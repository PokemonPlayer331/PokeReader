
#!/usr/bin/env python3
"""V7.1: manual reset test after releasing physical buttons."""
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

if any('ROWLET_V7_RESET_TEST' in s for s in (m, h, d)):
    raise SystemExit('V7 already applied')

checks = [
    ('A injector', 'bool rowlet_try_inject_a_frame(void)', h),
    ('HID header', 'bool rowlet_try_inject_a_frame(void);', d),
    ('A hook', '        rowlet_a_test_tick();', m),
    ('render', '        draw_to_screen(screenId, fb_a, stride, format);', m),
    ('hook', 'void run_hook(', m),
]
for label, anchor, content in checks:
    if content.count(anchor) != 1:
        raise SystemExit(f'Could not find {label} exactly once')

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
// States: ready, wait release, send, attempted, failed.
static unsigned int reset_status = 0;
static unsigned int reset_idle = 0;
static unsigned int reset_hold = 0;
static unsigned int reset_pulse = 0;
static unsigned int reset_wait = 0;
static bool reset_armed = false;

static void rowlet_reset_test_tick(void)
{
    if (get_title_id() != 0x00040000001B5000ULL)
        return;

    const u32 keys = get_current_keys();
    const u32 trigger = KEY_L | KEY_X | KEY_B;

    if (reset_status == 0 && !reset_armed)
    {
        reset_idle = (keys == 0) ? reset_idle + 1 : 0;
        if (reset_idle >= 30)
            reset_armed = true;
    }

    if (reset_status == 0 && reset_armed)
    {
        reset_hold = (keys == trigger) ? reset_hold + 1 : 0;

        if (reset_hold >= 60)
        {
            reset_armed = false;
            reset_status = 1;
            reset_idle = 0;
            reset_wait = 0;
        }
    }
    else if (reset_status == 1)
    {
        // Wait for ALL physical buttons to be released.
        if (keys & KEY_SELECT)
        {
            reset_status = 4;
            return;
        }

        reset_idle = (keys == 0) ? reset_idle + 1 : 0;

        if (reset_idle >= 15)
        {
            reset_status = 2;
            reset_pulse = 0;
        }
        else if (++reset_wait >= 600)
        {
            reset_status = 4;
        }
    }
    else if (reset_status == 2)
    {
        if (!rowlet_try_inject_reset_frame())
        {
            reset_status = 4;
            return;
        }

        if (++reset_pulse >= 45)
            reset_status = 3;
    }
}
'''

m = m.replace(
    'void run_hook(',
    controller + 'void run_hook(',
    1
)

m = m.replace(
    '        rowlet_a_test_tick();',
    '        rowlet_a_test_tick();\n'
    '        rowlet_reset_test_tick();',
    1
)

m = m.replace(
    '        draw_to_screen(screenId, fb_a, stride, format);',
    '''        if (get_title_id() == 0x00040000001B5000ULL)
        {
            const char *label = 0;

            if (reset_status == 1)
                label = "RESET TEST: RELEASE BUTTONS";
            if (reset_status == 2)
                label = "RESET TEST: SENDING";
            if (reset_status == 3)
                label = "RESET TEST: ATTEMPTED";
            if (reset_status == 4)
                label = "RESET TEST: FAILED";

            if (label)
                host_print(
                    (u32)label,
                    strlen(label),
                    0x00ff00);
        }

        draw_to_screen(screenId, fb_a, stride, format);''',
    1
)

hid.write_text(h)
hdr.write_text(d)
main.write_text(m)

print("V7.1 patch applied.")
print("Hold L+X+B for one second, then release.")
print("No automatic resets enabled.")
