//! Diagnostic-only Rowlet observer: no inputs, resets or memory writes.
pub const TSV: u16 = 3936;
const ROWLET: u16 = 722;
const STABLE_FRAMES: u16 = 30;
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Phase { Standby, WaitRowlet, Verify, Normal, Shiny, Error }
impl Phase {
    pub fn label(self) -> &'static str {
        match self { Self::Standby => "Waiting for save", Self::WaitRowlet => "Wait for Rowlet",
            Self::Verify => "Verifying...", Self::Normal => "NORMAL: stop",
            Self::Shiny => "SHINY: STOP!", Self::Error => "ERROR: STOP" }
    }
}
#[derive(Clone, Copy)]
pub struct Sample { pub tsv: u16, pub species: u16, pub valid: bool,
    pub pid: u32, pub psv: u16, pub ot_tsv: u16, pub shiny: bool }
pub const fn psv(pid: u32) -> u16 { (((pid >> 16) ^ (pid & 0xffff)) >> 4) as u16 }
pub struct Watch {
    pub phase: Phase, pub pid: u32, pub psv: u16, pub tsv: u16,
    pub count: u32, pub frames: u16, pub message: &'static str,
}
impl Watch {
    pub const fn new() -> Self { Self { phase: Phase::Standby, pid: 0, psv: 0,
        tsv: 0, count: 0, frames: 0, message: "Reset disabled" } }
    fn fail(&mut self, why: &'static str) { self.phase = Phase::Error; self.message = why; }
    fn good(s: Sample) -> bool {
        s.valid && s.species == ROWLET && s.ot_tsv == s.tsv &&
        s.psv == psv(s.pid) && s.shiny == (s.psv == s.ot_tsv)
    }
    pub fn tick(&mut self, s: Sample) {
        if matches!(self.phase, Phase::Normal | Phase::Shiny | Phase::Error) { return; }
        self.tsv = s.tsv;
        // PokeReader starts before Ultra Sun loads a save. Never latch a
        // mismatch until the pre-starter save is present and slot 1 is empty.
        if self.phase == Phase::Standby {
            if s.tsv == TSV && s.species == 0 {
                self.frames = self.frames.saturating_add(1);
                if self.frames >= STABLE_FRAMES {
                    self.frames = 0; self.phase = Phase::WaitRowlet;
                    self.message = "Empty slot confirmed";
                }
            } else { self.frames = 0; }
            return;
        }
        if s.tsv != TSV { self.fail("Trainer TSV changed"); return; }
        match self.phase {
            Phase::WaitRowlet => {
                if s.species == 0 { return; }
                if !Self::good(s) { self.fail("Invalid Rowlet data"); return; }
                self.pid = s.pid; self.psv = s.psv;
                self.frames = 1; self.phase = Phase::Verify;
                self.message = "Checking stable PID";
            }
            Phase::Verify => {
                if !Self::good(s) || s.pid != self.pid || s.psv != self.psv {
                    self.fail("Rowlet data changed"); return;
                }
                self.frames = self.frames.saturating_add(1);
                if self.frames < STABLE_FRAMES { return; }
                self.count = self.count.saturating_add(1);
                if s.shiny { self.phase = Phase::Shiny; self.message = "DO NOT RESET!"; }
                else { self.phase = Phase::Normal; self.message = "Reset manually"; }
            }
            _ => {}
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn sample(pid: u32) -> Sample { Sample {tsv: TSV, species: ROWLET, valid: true,
        pid, psv: psv(pid), ot_tsv: TSV, shiny: psv(pid) == TSV} }
    fn arm(w: &mut Watch) { let s = Sample {tsv: TSV, species: 0, valid: false,
        pid: 0, psv: 0, ot_tsv: 0, shiny: false};
        for _ in 0..STABLE_FRAMES { w.tick(s); }
        assert_eq!(w.phase, Phase::WaitRowlet);
    }
    #[test] fn user_data() { assert_eq!(psv(0x6299E33B), 2074); }
    #[test] fn normal() { let mut w=Watch::new(); arm(&mut w);
        for _ in 0..STABLE_FRAMES { w.tick(sample(0x6299E33B)); }
        assert_eq!(w.phase, Phase::Normal); assert_eq!(w.count, 1); }
    #[test] fn shiny() { let mut w=Watch::new(); arm(&mut w);
        for _ in 0..STABLE_FRAMES { w.tick(sample(0xF6000000)); }
        assert_eq!(w.phase, Phase::Shiny); }
    #[test] fn waits_for_save() { let mut w=Watch::new(); let mut s=sample(0x6299E33B);
        s.tsv=1234; w.tick(s); assert_eq!(w.phase, Phase::Standby); }
    #[test] fn old_party_is_not_armed() { let mut w=Watch::new(); w.tick(sample(0x6299E33B));
        assert_eq!(w.phase, Phase::Standby); }
    #[test] fn trainer_changed_after_arming() { let mut w=Watch::new(); arm(&mut w);
        let mut s=sample(0x6299E33B); s.tsv=1234; w.tick(s);
        assert_eq!(w.phase, Phase::Error); }
    #[test] fn unstable_pid() { let mut w=Watch::new(); arm(&mut w);
        w.tick(sample(0x6299E33B)); w.tick(sample(0x6299E33C));
        assert_eq!(w.phase, Phase::Error); }
    #[test] fn invalid_record() { let mut w=Watch::new(); arm(&mut w);
        let mut s=sample(0x6299E33B); s.valid=false; w.tick(s);
        assert_eq!(w.phase, Phase::Error); }
}
