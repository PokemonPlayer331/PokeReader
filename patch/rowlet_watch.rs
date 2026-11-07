//! Rowlet Watch V5: fail-closed, diagnostic-only reset authorization.
//! NO key injection. NO automatic restart. NO memory writes.
//!
//! We only authorize a *hypothetical* reset when the game had an empty
//! party slot, generated a valid new Rowlet, and its PID / PSV remained
//! consistent through two separate verification windows.

pub const TSV: u16 = 3936;
const ROWLET: u16 = 722;
const EMPTY_FRAMES: u16 = 30;
const VERIFY_FRAMES: u16 = 30;
const REVERIFY_FRAMES: u16 = 30;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Phase {
    Standby,
    WaitRowlet,
    Verify,
    Reverify,
    Normal,
    Shiny,
    Error,
}

impl Phase {
    pub fn label(self) -> &'static str {
        match self {
            Self::Standby => "Waiting for save",
            Self::WaitRowlet => "Wait for Rowlet",
            Self::Verify => "Checking Rowlet (1/2)",
            Self::Reverify => "Checking Rowlet (2/2)",
            Self::Normal => "RESET APPROVED (DRY RUN)",
            Self::Shiny => "SHINY: STOP!",
            Self::Error => "ERROR: STOP",
        }
    }
}

#[derive(Clone, Copy)]
pub struct Sample {
    pub tsv: u16,
    pub species: u16,
    pub valid: bool,
    pub pid: u32,
    pub psv: u16,
    pub ot_tsv: u16,
    pub shiny: bool,
}

pub const fn psv(pid: u32) -> u16 {
    (((pid >> 16) ^ (pid & 0xffff)) >> 4) as u16
}

pub struct Watch {
    pub phase: Phase,
    pub pid: u32,
    pub psv: u16,
    pub tsv: u16,
    pub count: u32,
    pub frames: u16,
    pub message: &'static str,
}

impl Watch {
    pub const fn new() -> Self {
        Self {
            phase: Phase::Standby,
            pid: 0,
            psv: 0,
            tsv: 0,
            count: 0,
            frames: 0,
            message: "No reset buttons will be pressed",
        }
    }

    fn fail(&mut self, reason: &'static str) {
        self.phase = Phase::Error;
        self.message = reason;
    }

    fn verified_rowlet(s: Sample) -> bool {
        s.valid
            && s.species == ROWLET
            && s.tsv == TSV
            && s.ot_tsv == s.tsv
            && s.psv == psv(s.pid)
            && s.shiny == (s.psv == s.ot_tsv)
    }

    // This flag ONLY controls diagnostic UI. It does not cause game input.
    pub fn hypothetical_reset_approved(&self) -> bool {
        self.phase == Phase::Normal
    }

    pub fn tick(&mut self, s: Sample) {
        // Stop states latch. The player must manually soft reset for a new run.
        if matches!(self.phase, Phase::Normal | Phase::Shiny | Phase::Error) {
            return;
        }
        self.tsv = s.tsv;

        // Do not arm until the pre-starter save has a stable, empty slot 1.
        if self.phase == Phase::Standby {
            if s.tsv == TSV && s.species == 0 {
                self.frames = self.frames.saturating_add(1);
                if self.frames >= EMPTY_FRAMES {
                    self.phase = Phase::WaitRowlet;
                    self.frames = 0;
                    self.message = "Empty slot confirmed";
                }
            } else {
                self.frames = 0;
            }
            return;
        }

        if s.tsv != TSV {
            self.fail("Trainer TSV changed");
            return;
        }

        match self.phase {
            Phase::WaitRowlet => {
                if s.species == 0 { return; }
                if !Self::verified_rowlet(s) {
                    self.fail("Invalid Rowlet data");
                    return;
                }
                self.pid = s.pid;
                self.psv = s.psv;
                if s.shiny {
                    self.phase = Phase::Shiny;
                    self.message = "Do not reset!";
                } else {
                    self.frames = 1;
                    self.phase = Phase::Verify;
                    self.message = "Verifying new Rowlet";
                }
            }
            Phase::Verify | Phase::Reverify => {
                if !Self::verified_rowlet(s) || s.pid != self.pid || s.psv != self.psv {
                    self.fail("Rowlet data changed or invalid");
                    return;
                }
                if s.shiny {
                    self.phase = Phase::Shiny;
                    self.message = "Do not reset!";
                    return;
                }
                self.frames = self.frames.saturating_add(1);
                if self.phase == Phase::Verify && self.frames >= VERIFY_FRAMES {
                    self.phase = Phase::Reverify;
                    self.frames = 0;
                    self.message = "Second independent check";
                } else if self.phase == Phase::Reverify && self.frames >= REVERIFY_FRAMES {
                    self.phase = Phase::Normal;
                    self.count = self.count.saturating_add(1);
                    self.message = "Would reset; no buttons sent";
                    self.frames = 0;
                }
            }
            _ => {}
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn sample(pid: u32) -> Sample {
        Sample {
            tsv: TSV, species: ROWLET, valid: true, pid,
            psv: psv(pid), ot_tsv: TSV, shiny: psv(pid) == TSV,
        }
    }
    fn arm(w: &mut Watch) {
        let empty = Sample {
            tsv: TSV, species: 0, valid: false,
            pid: 0, psv: 0, ot_tsv: 0, shiny: false,
        };
        for _ in 0..EMPTY_FRAMES { w.tick(empty); }
        assert_eq!(w.phase, Phase::WaitRowlet);
    }
    #[test] fn known_rowlet_values() {
        assert_eq!(psv(0x6299E33B), 2074);
    }
    #[test] fn approval_is_never_early() {
        let mut w = Watch::new(); arm(&mut w);
        for _ in 0..(VERIFY_FRAMES + REVERIFY_FRAMES - 1) {
            w.tick(sample(0x6299E33B));
        }
        assert!(!w.hypothetical_reset_approved());
        w.tick(sample(0x6299E33B));
        assert!(w.hypothetical_reset_approved());
        assert_eq!(w.count, 1);
    }
    #[test] fn shiny_blocks_approval() {
        let mut w = Watch::new(); arm(&mut w);
        w.tick(sample(0xF6000000));
        assert_eq!(w.phase, Phase::Shiny);
        assert!(!w.hypothetical_reset_approved());
    }
    #[test] fn mismatched_pid_blocks_approval() {
        let mut w = Watch::new(); arm(&mut w);
        w.tick(sample(0x6299E33B));
        w.tick(sample(0x6299E33C));
        assert_eq!(w.phase, Phase::Error);
        assert!(!w.hypothetical_reset_approved());
    }
    #[test] fn invalid_data_blocks_approval() {
        let mut w = Watch::new(); arm(&mut w);
        let mut s = sample(0x6299E33B);
        s.valid = false;
        w.tick(s);
        assert_eq!(w.phase, Phase::Error);
    }
    #[test] fn loaded_old_rowlet_cannot_arm() {
        let mut w = Watch::new();
        for _ in 0..100 { w.tick(sample(0x6299E33B)); }
        assert_eq!(w.phase, Phase::Standby);
        assert!(!w.hypothetical_reset_approved());
    }
    #[test] fn changing_tsv_stops() {
        let mut w = Watch::new(); arm(&mut w);
        let mut s = sample(0x6299E33B);
        s.tsv = 1234;
        w.tick(s);
        assert_eq!(w.phase, Phase::Error);
    }
}
