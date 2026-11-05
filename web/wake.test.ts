import assert from "node:assert/strict";
import test from "node:test";
import { commandAfterWake } from "./src/wake.ts";

test("hey orion with a command is the command", () => {
  assert.equal(commandAfterWake("Hey Orion, what time is it?", false), "what time is it");
});

test("orion alone wakes and waits", () => {
  assert.equal(commandAfterWake("Orion", false), "");
});

test("a bare hello is ignored until he is awake", () => {
  assert.equal(commandAfterWake("hello", false), null);
  assert.equal(commandAfterWake("hello", true), "hello");
});
