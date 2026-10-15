/**
 * Progress for the two slow tools: cloning and tagging.
 *
 * MCP's channel for this is `notifications/progress`, tied to the
 * `_meta.progressToken` the client put on the request. TypeScript-SDK clients
 * that opt into `resetTimeoutOnProgress` restart their 60 s request timeout on
 * each frame, and a clone of a state plus Congress runs well past 60 s, so
 * progress can decide whether the call completes or times out on the client.
 *
 * The CLI has little to say while it works. `govbot clone` prints one line when it
 * starts, one line per repository *after* that repository finishes, and a
 * summary. `govbot tag` prints its mode and, the first time only, that it is
 * downloading the model. So a heartbeat runs on a timer and reports elapsed
 * time, and the CLI's lines only refine what it says.
 */

/** One progress frame, without the token (the sender adds it). */
export interface ProgressUpdate {
  /** Must go up with every frame (spec requirement), even when `total` is unknown. */
  progress: number;
  total?: number;
  message: string;
}

/** Sends one frame. Absent when the client did not ask for progress. */
export type SendProgress = (update: ProgressUpdate) => void;

/** How often the heartbeat speaks. Well under the 60 s default client timeout. */
export const HEARTBEAT_MS = 5_000;

export interface Tracker {
  /** Feed raw stderr chunks from the CLI; partial lines are buffered. */
  stderr(chunk: string): void;
  /** Stop the heartbeat. Safe to call more than once. */
  stop(): void;
}

export interface TrackerOptions {
  intervalMs?: number;
  now?: () => number;
}

/** "3 s", "1 min 31 s". */
export function formatElapsed(ms: number): string {
  const seconds = Math.max(0, Math.round(ms / 1000));
  if (seconds < 60) return `${seconds} s`;
  return `${Math.floor(seconds / 60)} min ${seconds % 60} s`;
}

/** What the person would call a locale. `usa` is the one code nobody reads as Congress. */
function label(locale: string): string {
  return locale === "usa" ? "Congress" : locale.toUpperCase();
}

/**
 * Send `describe(elapsed)` now and every `intervalMs` until stopped. `emit` is
 * also exposed so a CLI line that changes the picture is reported at once.
 *
 * Frames whose `progress` would not go up are dropped rather than sent: the spec
 * requires an increase, and a client may reject or mis-draw anything else.
 */
function heartbeat(
  send: SendProgress,
  describe: (elapsedMs: number) => ProgressUpdate,
  options: TrackerOptions,
) {
  const now = options.now ?? Date.now;
  const started = now();
  const elapsed = () => now() - started;
  let last = -Infinity;

  const emit = () => {
    const update = describe(elapsed());
    if (!(update.progress > last)) return;
    last = update.progress;
    try {
      send(update);
    } catch {
      // Progress is best-effort; it must never fail the tool call.
    }
  };

  emit();
  const timer = setInterval(emit, options.intervalMs ?? HEARTBEAT_MS);
  return { emit, elapsed, stop: () => clearInterval(timer) };
}

/** Split stderr chunks into whole lines; a line can straddle two chunks. */
function lineSplitter(onLine: (line: string) => void): (chunk: string) => void {
  let buffered = "";
  return (chunk) => {
    buffered += chunk;
    const lines = buffered.split("\n");
    buffered = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed) onLine(trimmed);
    }
  };
}

/**
 * Progress for `govbot clone <locales…>`.
 *
 * `total` is the number of jurisdictions. Between completions `progress` creeps
 * toward the next whole number without reaching it (t / (t + 30) of the way, t
 * in seconds since the last completion), so it rises on every heartbeat however
 * long one repository takes, and a completion always moves it up.
 *
 * Edge case: the CLI prints a repository's size only once it has finished, so
 * sizes are reported for finished jurisdictions, never predicted.
 */
export function trackClone(
  locales: string[],
  send: SendProgress,
  options: TrackerOptions = {},
): Tracker {
  const done = new Map<string, string>(); // locale -> " (1.4 GB)", " (failed)" or ""
  let lastCompletionMs = 0;

  const describe = (elapsedMs: number): ProgressUpdate => {
    const pending = locales.filter((l) => !done.has(l));
    const finished = [...done].map(([l, note]) => `${label(l)}${note}`);
    const sinceCompletion = Math.max(0, elapsedMs - lastCompletionMs) / 1000;
    const creep = pending.length ? sinceCompletion / (sinceCompletion + 30) : 0;
    const doing = pending.length
      ? `Downloading ${pending.map(label).join(", ")}`
      : "Finishing up";
    return {
      progress: done.size + creep,
      total: locales.length,
      message:
        (finished.length ? `Done: ${finished.join(", ")}. ` : "") +
        `${doing}: ${formatElapsed(elapsedMs)} so far`,
    };
  };

  const beat = heartbeat(send, describe, options);

  const onLine = lineSplitter((line) => {
    // Per-repository result, printed when that repository is finished:
    //   "🆕  il      [1.4 GB]", "✅  wy      [210 MB -> 212 MB]", "❌  il      <error>"
    // The start and summary lines ("🔁 Syncing 2 repos", "✅ Successfully …")
    // never match, because their second word is capitalised.
    const match = line.match(/^(\S+)\s+([a-z]{2,3})(?:\s+\[(.+)\])?(?:\s|$)/);
    if (!match) return;
    const [, mark, locale, size] = match;
    if (!locale || !locales.includes(locale) || done.has(locale)) return;
    done.set(locale, mark === "❌" ? " (failed)" : size ? ` (${size})` : "");
    lastCompletionMs = beat.elapsed();
    beat.emit();
  });

  return { stderr: onLine, stop: beat.stop };
}

/**
 * Progress for `govbot logs | govbot tag`.
 *
 * The CLI gives no count of bills scored, so there is no `total`; `progress` is
 * elapsed seconds. The one line worth reacting to is the first-run model
 * download, which can take longer than the scoring itself.
 */
export function trackTag(
  limitPerJurisdiction: number,
  send: SendProgress,
  options: TrackerOptions = {},
): Tracker {
  let phase = `Scoring up to ${limitPerJurisdiction} bills per jurisdiction`;

  const beat = heartbeat(
    send,
    (elapsedMs) => ({
      progress: elapsedMs / 1000,
      message: `${phase}: ${formatElapsed(elapsedMs)} so far`,
    }),
    options,
  );

  const onLine = lineSplitter((line) => {
    if (/^Embedding files not found/.test(line)) {
      phase = "Downloading the local AI model (first time only)";
    } else if (/Successfully downloaded embedding files/.test(line)) {
      phase = `Model ready. Scoring up to ${limitPerJurisdiction} bills per jurisdiction`;
    } else {
      return;
    }
    beat.emit();
  });

  return { stderr: onLine, stop: beat.stop };
}
