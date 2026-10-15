/**
 * Tests for progress on the slow tools.
 *
 * What matters: frames keep coming while the CLI is silent (so clients that reset
 * their timeout on progress do not give up), `progress` only ever goes up (the
 * spec requires it), and nothing is sent at all when the client did not ask.
 */

import assert from "node:assert/strict";
import { test, mock } from "node:test";

import {
  formatElapsed,
  HEARTBEAT_MS,
  trackClone,
  trackTag,
  type ProgressUpdate,
} from "./progress.js";

/** A fake clock driving both `now` and the heartbeat's setInterval. */
function fakeClock() {
  mock.timers.enable({ apis: ["setInterval"] });
  let t = 0;
  return {
    now: () => t,
    advance(ms: number) {
      t += ms;
      mock.timers.tick(ms);
    },
    reset: () => mock.timers.reset(),
  };
}

function assertIncreasing(frames: ProgressUpdate[]) {
  for (let i = 1; i < frames.length; i++) {
    assert.ok(
      frames[i]!.progress > frames[i - 1]!.progress,
      `progress went ${frames[i - 1]!.progress} -> ${frames[i]!.progress}`,
    );
  }
}

test("a silent 12 s clone still sends a frame at least every 5 s, always going up", () => {
  const clock = fakeClock();
  const frames: ProgressUpdate[] = [];
  const tracker = trackClone(["il"], (u) => frames.push(u), { now: clock.now });

  for (let i = 0; i < 12; i++) clock.advance(1000);
  tracker.stop();
  clock.advance(HEARTBEAT_MS * 3); // nothing after stop
  clock.reset();

  // t = 0, 5, 10.
  assert.equal(frames.length, 3);
  assertIncreasing(frames);
  for (const frame of frames) {
    assert.equal(frame.total, 1);
    assert.ok(frame.progress < 1, "not done until the CLI says so");
  }
  assert.equal(frames.at(-1)!.message, "Downloading IL: 10 s so far");
});

test("each finished repository moves progress to the next whole number and names its size", () => {
  const clock = fakeClock();
  const frames: ProgressUpdate[] = [];
  const tracker = trackClone(["il", "usa"], (u) => frames.push(u), { now: clock.now });

  tracker.stderr("🔁 Syncing 2 repos\n\n");
  clock.advance(HEARTBEAT_MS * 6);
  // Split across chunks, as a pipe can deliver it.
  tracker.stderr("🆕  usa     [1.");
  tracker.stderr("5 GB]\n");
  const afterUsa = frames.at(-1)!;
  assert.equal(afterUsa.progress, 1);
  assert.equal(afterUsa.message, "Done: Congress (1.5 GB). Downloading IL: 30 s so far");

  clock.advance(HEARTBEAT_MS);
  assert.ok(frames.at(-1)!.progress > 1 && frames.at(-1)!.progress < 2);

  tracker.stderr("🆕  il      [1.4 GB]\n\n✅ Successfully processed all 2 repos!\n");
  assert.equal(frames.at(-1)!.progress, 2);
  tracker.stop();
  clock.reset();

  assertIncreasing(frames);
  assert.ok(frames.every((f) => f.total === 2));
});

test("progress keeps rising through a very long single download", () => {
  // A slow home connection can take many minutes on one state; the creep toward
  // the next whole number must stay strictly increasing the whole way.
  const clock = fakeClock();
  const frames: ProgressUpdate[] = [];
  const tracker = trackClone(["il"], (u) => frames.push(u), { now: clock.now });
  for (let i = 0; i < (15 * 60 * 1000) / HEARTBEAT_MS; i++) clock.advance(HEARTBEAT_MS);
  tracker.stop();
  clock.reset();

  assert.equal(frames.length, 15 * 60 / 5 + 1);
  assertIncreasing(frames);
  assert.ok(frames.at(-1)!.progress < 1);
});

test("a failed repository counts as finished and says so", () => {
  const clock = fakeClock();
  const frames: ProgressUpdate[] = [];
  const tracker = trackClone(["wy", "gu"], (u) => frames.push(u), { now: clock.now });
  tracker.stderr("❌  gu      network unreachable\n");
  tracker.stop();
  clock.reset();
  assert.equal(frames.at(-1)!.progress, 1);
  assert.match(frames.at(-1)!.message, /^Done: GU \(failed\)\. Downloading WY/);
});

test("tagging heartbeats, and switches its message for the first-run model download", () => {
  const clock = fakeClock();
  const frames: ProgressUpdate[] = [];
  const tracker = trackTag(400, (u) => frames.push(u), { now: clock.now });

  clock.advance(HEARTBEAT_MS);
  tracker.stderr("Embedding files not found. Downloading all-MiniLM-L6-v2 (ONNX) to /x...\n");
  clock.advance(HEARTBEAT_MS);
  tracker.stop();
  clock.reset();

  assertIncreasing(frames);
  assert.ok(frames.every((f) => f.total === undefined));
  assert.equal(frames[0]!.message, "Scoring up to 400 bills per jurisdiction: 0 s so far");
  assert.equal(
    frames.at(-1)!.message,
    "Downloading the local AI model (first time only): 10 s so far",
  );
});

test("a sender that throws never breaks the tool", () => {
  const clock = fakeClock();
  const tracker = trackClone(["wy"], () => {
    throw new Error("transport closed");
  }, { now: clock.now });
  clock.advance(HEARTBEAT_MS * 2);
  tracker.stderr("🆕  wy      [212 MB]\n");
  tracker.stop();
  clock.reset();
});

test("elapsed time reads the way a person would say it", () => {
  assert.equal(formatElapsed(3_300), "3 s");
  assert.equal(formatElapsed(59_400), "59 s");
  assert.equal(formatElapsed(91_000), "1 min 31 s");
});
