import { describe, expect, it } from "vitest";
import { acceptFrame, catchUp, fcmBody, type RoomState } from "../src/frames";

const empty: RoomState = { pcOnline: false, phones: 0, queue: [] };

describe("relay frames", () => {
  it("tells a phone the PC is offline", () => {
    const result = acceptFrame(empty, "phone", { type: "chat", id: "1", text: "hi" });
    expect(result.deliver).toBe("sender");
    expect(result.frame.text).toBe("offline");
  });

  it("routes chat to the PC and replies back to phones", () => {
    const online = acceptFrame(empty, "pc", { type: "hello", role: "pc" });
    expect(online.state.pcOnline).toBe(true);
    const chat = acceptFrame(online.state, "phone", { type: "chat", id: "2", text: "time" });
    expect(chat.deliver).toBe("pc");
    const reply = acceptFrame(chat.state, "pc", { type: "reply", id: "2", text: "noon" });
    expect(reply.deliver).toBe("phones");
  });

  it("keeps the last events for a phone that reconnects", () => {
    let state = { ...empty, pcOnline: true };
    for (let i = 0; i < 60; i += 1) {
      state = acceptFrame(state, "pc", { type: "event", kind: "reminder", text: String(i) }).state;
    }
    expect(catchUp(state)).toHaveLength(50);
    expect(catchUp(state)[49].text).toBe("59");
  });

  it("rejects an oversized audio frame", () => {
    const result = acceptFrame({ ...empty, pcOnline: true }, "phone", { type: "audio", text: "x".repeat(1_000_001) });
    expect(result.frame.type).toBe("error");
  });

  it("builds an FCM body without the chat text beyond the event", () => {
    const body = fcmBody("phone-token", { type: "event", kind: "battery", text: "Battery is at 10 percent." });
    expect(body.token).toBe("phone-token");
    expect(body.data.kind).toBe("battery");
  });
});
