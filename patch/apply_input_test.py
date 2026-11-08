
#!/usr/bin/env python3
"""Experimental V6 single-A input test for PokeReader.

No automatic soft resets or starter selection.
"""

from pathlib import Path
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("repo", nargs="?", default=".")
root = Path(parser.parse_args().repo).resolve()

main = root / "3gx/sources/main.c"
hid = root / "3gx/sources/hid.c"
hdr = root / "3gx/includes/hid.h"

for path in (main, hid, hdr):
    if not path.is_file():
        raise SystemExit(
            f"Missing PokeReader file: {path}"
        )

m = main.read_text()
h = hid.read_text()
d = hdr.read_text()

marker = "ROWLET_V6_INPUT_TEST"

if any(marker in s for s in (m, h, d)):
    raise SystemExit("V6 already patched.")

old_hook = """        scan_input();
        run_frame();
        draw_to_screen(screenId, fb_a, stride, format);"""

if m.count(old_hook) != 1:
    raise SystemExit("Main hook not found.")

if m.count("void run_hook(") != 1:
    raise SystemExit("Invalid run_hook count.")

if h.count("void set_key_addr(") != 1:
    raise SystemExit("HID source changed.")

if d.count("void scan_input()") != 1:
    raise SystemExit("HID header changed.")

# V6 FIX: Include PokeReader's SVC declarations.
h = h.replace(
    "#include <3ds.h>",
    '#include <3ds.h>\n'
    '#include "common.h"\n'
    '#include "csvc.h"',
    1
)

h += """
// ROWLET_V6_INPUT_TEST
// Experimental A-button injection.

bool rowlet_try_inject_a_frame(void)
{
    if (!g_key_addr)
        return false;

    volatile u32 *base =
        g_key_addr - (0x28 / 4);

    u32 index = base[0x10 / 4];

    if (index >= 8)
        return false;

    volatile u32 *sample =
        base + (0x28 / 4) +
        index * (0x10 / 4);

    u32 sample_pa = svcConvertVAToPA(
        (const void *)sample,
        false
    );

    u32 current_pa = svcConvertVAToPA(
        (const void *)(base + (0x1c / 4)),
        false
    );

    if (!sample_pa || !current_pa)
        return false;

    volatile u32 *s =
        (volatile u32 *)(
            sample_pa | 0x80000000u
        );

    volatile u32 *cur =
        (volatile u32 *)(
            current_pa | 0x80000000u
        );

    s[0] |= KEY_A;
    s[1] |= KEY_A;
    *cur |= KEY_A;

    return true;
}
"""

d += """
// ROWLET_V6_INPUT_TEST
bool rowlet_try_inject_a_frame(void);
"""

controller = """
// ROWLET_V6_INPUT_TEST

static unsigned int rowlet_a_test_state = 0;
static unsigned int rowlet_a_test_frames = 0;
static bool rowlet_a_test_latch = false;

static void rowlet_a_test_tick(void)
{
    if (get_title_id() !=
        0x00040000001B5000ULL)
        return;

    const u32 keys = get_current_keys();
    const u32 trigger =
        KEY_L | KEY_X | KEY_Y;

    if (rowlet_a_test_state == 0 &&
        !rowlet_a_test_latch &&
        keys == trigger)
    {
        rowlet_a_test_latch = true;
        rowlet_a_test_state = 1;
        rowlet_a_test_frames = 0;
    }

    if (rowlet_a_test_state == 1 &&
        (keys & (KEY_B | KEY_R |
                 KEY_START | KEY_SELECT)))
    {
        rowlet_a_test_state = 3;
        return;
    }

    if (rowlet_a_test_state == 1)
    {
        if (!rowlet_try_inject_a_frame())
        {
            rowlet_a_test_state = 3;
            return;
        }

        rowlet_a_test_frames++;

        if (rowlet_a_test_frames >= 8)
            rowlet_a_test_state = 2;
    }
}

"""

m = m.replace(
    "void run_hook(",
    controller + "void run_hook(",
    1
)

new_hook = """        scan_input();
        rowlet_a_test_tick();
        run_frame();

        if (get_title_id() ==
            0x00040000001B5000ULL)
        {
            const char *label = 0;

            if (rowlet_a_test_state == 0)
                label = "A TEST READY: L+X+Y";

            if (rowlet_a_test_state == 1)
                label = "A TEST: PULSING";

            if (rowlet_a_test_state == 2)
                label = "A TEST: ATTEMPTED";

            if (rowlet_a_test_state == 3)
                label = "A TEST: FAILED/CANCELLED";

            if (label)
                host_print(
                    (u32)label,
                    strlen(label),
                    0x00ff00
                );
        }

        draw_to_screen(screenId, fb_a, stride, format);"""

m = m.replace(old_hook, new_hook, 1)

hid.write_text(h)
hdr.write_text(d)
main.write_text(m)

print("V6 input test patch applied.")
print("Missing SVC header declaration fixed.")
print("No automatic resets enabled.")
print("Test trigger: L+X+Y")
