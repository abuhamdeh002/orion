export type Frame = {
  type: string;
  id?: string;
  role?: "pc" | "phone";
  text?: string;
  action?: string;
  arguments?: Record<string, unknown>;
  kind?: string;
  device?: string;
};

export type RoomState = {
  pcOnline: boolean;
  phones: number;
  queue: Frame[];
};

const QUEUE_LIMIT = 50;
const AUDIO_LIMIT = 1_000_000;

export function acceptFrame(state: RoomState, from: "pc" | "phone", frame: Frame): { deliver: "pc" | "phones" | "sender" | "none"; frame: Frame; state: RoomState } {
  if (frame.type === "audio" && JSON.stringify(frame).length > AUDIO_LIMIT) {
    return { deliver: "sender", frame: { type: "error", id: frame.id, text: "Audio is too large." }, state };
  }
  if (frame.type === "hello" && from === "pc") {
    return { deliver: "phones", frame: { type: "presence", text: "online" }, state: { ...state, pcOnline: true } };
  }
  if (frame.type === "hello" && from === "phone") {
    const presence = state.pcOnline ? "online" : "offline";
    return { deliver: "sender", frame: { type: "presence", text: presence }, state: { ...state, phones: state.phones + 1 } };
  }
  if (from === "phone" && (frame.type === "chat" || frame.type === "do" || frame.type === "audio")) {
    if (!state.pcOnline) {
      return { deliver: "sender", frame: { type: "presence", text: "offline", id: frame.id }, state };
    }
    return { deliver: "pc", frame, state };
  }
  if (from === "pc" && (frame.type === "reply" || frame.type === "ack" || frame.type === "token" || frame.type === "confirm")) {
    return { deliver: "phones", frame, state };
  }
  if (from === "pc" && frame.type === "event") {
    const queue = [...state.queue, frame].slice(-QUEUE_LIMIT);
    return { deliver: "phones", frame, state: { ...state, queue } };
  }
  return { deliver: "none", frame, state };
}

export function catchUp(state: RoomState): Frame[] {
  return state.queue;
}

export function fcmBody(token: string, frame: Frame): { token: string; notification: { title: string; body: string }; data: { kind: string } } {
  return {
    token,
    notification: { title: "ORION", body: frame.text || frame.kind || "Update" },
    data: { kind: frame.kind || "note" },
  };
}
