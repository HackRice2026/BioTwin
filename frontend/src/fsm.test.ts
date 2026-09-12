import { describe, it, expect } from "vitest";
import { AvatarFSM } from "./fsm";

describe("Avatar activity state machine", () => {
  it("traverses exertion and recovery without a scripted animation sequence", () => {
    const fsm = new AvatarFSM();
    const d = { exertion: 0, fatigue: 0.7, recovery_progress: 0 };
    expect(fsm.update(d, 0)).toBe("IDLE");
    expect(fsm.update({ ...d, exertion: 0.4 }, 1)).toBe("EXERTION_RISING");
    expect(fsm.update({ ...d, exertion: 0.8 }, 3)).toBe("EXERTION_RISING");
    expect(fsm.update({ ...d, exertion: 0.8 }, 7)).toBe("EXERCISING");
    expect(fsm.update(d, 10)).toBe("EXERTION_FALLING");
    expect(fsm.update(d, 13)).toBe("FATIGUED");
    expect(fsm.update({ ...d, recovery_progress: 0.5 }, 20)).toBe("FATIGUED");
    expect(fsm.update({ ...d, recovery_progress: 0.5 }, 74)).toBe("RECOVERING");
    expect(fsm.update({ ...d, recovery_progress: 0.95 }, 100)).toBe("RESTORED");
    expect(fsm.update({ ...d, recovery_progress: 1 }, 106)).toBe("IDLE");
  });
  it("returns to rising exertion when activity resumes during recovery", () => {
    const fsm = new AvatarFSM();
    fsm.state = "RECOVERING";
    expect(
      fsm.update({ exertion: 0.8, fatigue: 0.4, recovery_progress: 0.3 }, 20),
    ).toBe("EXERTION_RISING");
  });
});
