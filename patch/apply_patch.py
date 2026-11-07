#!/usr/bin/env python3
"""Patch a FRESH PokeReader checkout with an Ultra Sun diagnostic Watch screen."""
import argparse
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('pokereader_folder', type=Path)
root = ap.parse_args().pokereader_folder.expanduser().resolve()
frame = root / 'reader_core/src/gen7/frame.rs'
mod = root / 'reader_core/src/gen7/mod.rs'
new = root / 'reader_core/src/gen7/rowlet_watch.rs'
if not frame.exists() or not mod.exists() or new.exists():
    raise SystemExit('Expected a fresh, unmodified PokeReader source folder. No changes made.')

f = frame.read_text()
m = mod.read_text()

def patch(txt, old, replacement):
    if txt.count(old) != 1:
        raise ValueError(f'Expected exactly one anchor ({txt.count(old)}): {old!r}; no changes made.')
    return txt.replace(old, replacement, 1)

try:
    m = patch(m, 'mod reader;', 'mod reader;\nmod rowlet_watch;')
    f = patch(f, 'use once_cell::unsync::Lazy;',
              'use once_cell::unsync::Lazy;\nuse pkm_rs::Pkx;\nuse super::rowlet_watch::{Sample, Watch};')
    f = patch(f, '    Party,\n', '    Party,\n    RowletWatch,\n')
    f = patch(f, '    party_menu: SubMenu,', '    party_menu: SubMenu,\n    rowlet_watch: Watch,')
    f = patch(f, '    MenuOption::new(Gen7View::Party, "Party"),',
              '    MenuOption::new(Gen7View::Party, "Party"),\n    MenuOption::new(Gen7View::RowletWatch, "Rowlet Watch"),')
    f = patch(f, '        party_menu: SubMenu::new(1, 6),',
              '        party_menu: SubMenu::new(1, 6),\n        rowlet_watch: Watch::new(),')
    f = patch(f, 'fn run_frame(reader: Gen7Reader) {',
              'fn run_frame(reader: Gen7Reader, is_ultra_sun: bool) {')
    anchor = '    state.sfmt.reinit_if_needed(reader.init_seed());'
    insert = '''    // Observe once each rendered game frame, including when overlay is hidden.
    // Use the *decoded* Pk7 record from PokeReader; no direct raw PID offsets.
    if is_ultra_sun {
        let mon = reader.party_pkm(0);
        state.rowlet_watch.tick(Sample {
            tsv: reader.tsv(),
            species: mon.species(),
            valid: mon.is_valid(),
            pid: mon.pid(),
            psv: mon.psv(),
            ot_tsv: mon.tsv(),
            shiny: mon.is_shiny(),
        });
    }

'''
    f = patch(f, anchor, insert + anchor)
    anchor = '        Gen7View::Box => draw_pkx(&reader.box_pkm(), PkxType::Tame),'
    insert = '''        Gen7View::RowletWatch => {
            let w = &state.rowlet_watch;
            pnp::println!("ROWLET WATCH v4");
            pnp::println!("{}", w.phase.label());
            pnp::println!("{}", w.message);
            pnp::println!("TSV: {}", w.tsv);
            pnp::println!("PID: {:08X}", w.pid);
            pnp::println!("PSV: {}", w.psv);
            pnp::println!("Stable frames: {}", w.frames);
            pnp::println!("Seen: {}", w.count);
            pnp::println!("Reset output: OFF");
        },'''
    f = patch(f, anchor, anchor + '\n' + insert)
    if f.count('    run_frame(reader)\n}') != 2:
        raise ValueError('Expected exactly two Gen7 frame call sites.')
    f = f.replace('    run_frame(reader)\n}', '    run_frame(reader, false)\n}', 1)
    f = patch(f, '    run_frame(reader)\n}',
              '    run_frame(reader, matches!(crate::title::loaded_title(), Ok(crate::title::LoadedTitle::Us)))\n}')
except ValueError as err:
    raise SystemExit(str(err))

# All checks succeeded, so it is safe to modify files.
frame.write_text(f)
mod.write_text(m)
new.write_text((Path(__file__).parent / 'rowlet_watch.rs').read_text())
print('Rowlet Watch diagnostic menu added to PokeReader.')
print('Automatic soft resetting and button inputs remain DISABLED.')
