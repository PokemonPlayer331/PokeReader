
#!/usr/bin/env python3
"""V7 manual soft-reset test, applied after V6."""
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
main = root / '3gx/sources/main.c'
hid = root / '3gx/sources/hid.c'
hdr = root / '3gx/includes/hid.h'

for path in (main, hid, hdr):
    if not path.is_file():
        raise SystemExit(f'Missing file: {path}')

m, h, d = main.read_text(), hid.read_text(), hdr.read_text()
marker = 'ROWLET_V7_RESET_TEST'

if any(marker in s for s in (m, h, d)):
    raise SystemExit('V7 already applied')

checks = [
    ('V6 injector', 'bool rowlet_try_inject_a_frame(void)', h),
    ('V6 header', 'bool rowlet_try_inject_a_frame(void);', d),
    ('V6 hook', '        rowlet_a_test_tick();', m),
    ('render', '        draw_to_screen(screenId, fb_a, stride, format);', m),
    ('run_hook', 'void run_hook(', m),
]

for label, anchor, content in checks:
    if content.count(anchor) != 1:
        raise SystemExit(f'{label} missing or duplicated')

h += r'''
// ROWLET_V7_RESET_TEST
bool rowlet_try_inject_reset_frame(void)
{
    if (!g_key_addr) return false;
    volatile u32 *base = g_key_addr - (0x28 / 4);
    u32 index = base[0x10 / 4];
    if (index >= 8) return false;

    volatile u32 *sample =
        base + (0x28 / 4) + index * (0x10 / 4);

    u32 sample_pa =
        svcConvertVAToPA((const void *)sample, false);
    u32 current_pa =
        svcConvertVAToPA(
            (const void *)(base + (0x1c / 4)), false);

    if (!sample_pa || !current_pa) return false;

    volatile u32 *s =
        (volatile u32 *)(sample_pa | 0x80000000u);
    volatile u32 *cur =
        (volatile u32 *)(current_pa | 0x80000000u);

    const u32 combo = KEY_L | KEY_R | KEY_START;
    s[0] |= combo;
    s[1] |= combo;
    *cur |= combo;
    return true;
}
'''

d += '''
// ROWLET_V7_RESET_TEST
bool rowlet_try_inject_reset_frame(void);
'''

controller = r'''
// ROWLET_V7_RESET_TEST
// Manual trigger only: hold L+X+B.
static unsigned int rowlet_reset_status = 0;
static unsigned int rowlet_reset_idle = 0;
static unsigned int rowlet_reset_hold = 0;
static unsigned int rowlet_reset_pulse = 0;
static bool rowlet_reset_armed = false;

static void rowlet_reset_test_tick(void)
{
    if (get_title_id() != 0x00040000001B5000ULL)
        return;

    const u32 keys = get_current_keys();
    const u32 trigger = KEY_L | KEY_X | KEY_B;

    if (!rowlet_reset_armed)
    {
        rowlet_reset_idle =
            (keys == 0) ? rowlet_reset_idle + 1 : 0;

        if (rowlet_reset_idle >= 30)
            rowlet_reset_armed = true;
    }

    if (rowlet_reset_status == 0 && rowlet_reset_armed)
    {
        rowlet_reset_hold =
            (keys == trigger) ? rowlet_reset_hold + 1 : 0;

        if (rowlet_reset_hold >= 60)
        {
            rowlet_reset_armed = false;
            rowlet_reset_status = 1;
            rowlet_reset_pulse = 0;
        }
    }

    if (rowlet_reset_status == 1)
    {
        if (keys & KEY_SELECT)
        {
            rowlet_reset_status = 3;
            return;
        }

        if (!rowlet_try_inject_reset_frame())
        {
            rowlet_reset_status = 3;
            return;
        }

        if (++rowlet_reset_pulse >= 20)
            rowlet_reset_status = 2;
    }
}
'''

m = m.replace(
    'void run_hook(',
    controller + 'void run_hook(', 1)

m = m.replace(
    '        rowlet_a_test_tick();',
    '        rowlet_a_test_tick();\n'
    '        rowlet_reset_test_tick();', 1)

m = m.replace(
    '        draw_to_screen(screenId, fb_a, stride, format);',
    '''        if (get_title_id() == 0x00040000001B5000ULL)
        {
            const char *reset_label = 0;
            if (rowlet_reset_status == 1)
                reset_label = "RESET TEST: SENDING";
            if (rowlet_reset_status == 2)
                reset_label = "RESET TEST: ATTEMPTED";
            if (rowlet_reset_status == 3)
                reset_label = "RESET TEST: FAILED";

            if (reset_label)
                host_print(
                    (u32)reset_label,
                    strlen(reset_label),
                    0x00ff00);
        }
        draw_to_screen(screenId, fb_a, stride, format);''', 1)

hid.write_text(h)
hdr.write_text(d)
main.write_text(m)

print("V7 manual reset test patched.")
print("Trigger: hold L+X+B for about one second.")
print("No automatic hunting or resetting enabled.")
