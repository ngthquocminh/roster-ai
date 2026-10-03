import { useRef, useState } from "react";
import { Link } from "react-router";

import { InlineAlert } from "@/components/primitives/InlineAlert";
import { Button } from "@/components/ui/button";

/**
 * Composer contract, verbatim from EXPERIENCE.md's *Keyboard and focus*:
 * `Enter` inserts a new line; `Ctrl+Enter` / `Command+Enter` sends. The visible
 * Send button is always available when sending is valid. Sending never triggers
 * Run optimization or approval — this component ships Send and nothing else
 * (UX-DR35).
 *
 * A `<textarea>` outside any `<form>` is deliberate: a `<form onSubmit>` would
 * submit on bare Enter, which is exactly what AC3 forbids.
 */
export function Composer({
  onSend,
  isPending,
  scenarioId,
  disabledReason,
}: Readonly<{
  onSend: (text: string) => Promise<unknown>;
  isPending: boolean;
  scenarioId: string;
  /** ID of the visible description explaining why agent actions are disabled. */
  disabledReason?: string;
}>) {
  const [draft, setDraft] = useState("");
  const [failed, setFailed] = useState(false);
  // `isPending` arrives a render late, so held or double-tapped Ctrl+Enter can
  // fire twice before it flips. Decision 4 ships no idempotency key and names
  // this disable as the sole double-submit defence, so the latch has to be
  // synchronous.
  const inFlight = useRef(false);

  const submit = async () => {
    const text = draft.trim();
    if (!text || isPending || disabledReason || inFlight.current) return;
    inFlight.current = true;
    setFailed(false);
    try {
      await onSend(text);
      // Clear on the success condition only. A recoverable failure must retain
      // the draft (AC3); clearing in the submit handler looks correct in every
      // manual test where the request happens to succeed.
      setDraft("");
    } catch {
      setFailed(true);
    } finally {
      inFlight.current = false;
    }
  };

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium" htmlFor="chat-composer">
        Message
      </label>
      <textarea
        aria-describedby={disabledReason}
        className="min-h-24 w-full rounded-lg border bg-background p-3 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        id="chat-composer"
        disabled={Boolean(disabledReason)}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
            event.preventDefault();
            void submit();
          }
        }}
        value={draft}
      />
      {failed ? (
        <InlineAlert
          action={
            <Link className="font-medium underline underline-offset-3" to={`/scenarios/${scenarioId}/data`}>
              Open Scenario Data
            </Link>
          }
          description="Your draft is still here — try sending again."
          title="Message could not be sent"
          variant="destructive"
        />
      ) : null}
      <div className="flex justify-end">
        <Button
          aria-describedby={disabledReason}
          className="min-h-11"
          disabled={!draft.trim() || isPending || Boolean(disabledReason)}
          onClick={() => void submit()}
          type="button"
        >
          Send
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Enter inserts a new line. Ctrl+Enter or Command+Enter sends.
      </p>
    </div>
  );
}
