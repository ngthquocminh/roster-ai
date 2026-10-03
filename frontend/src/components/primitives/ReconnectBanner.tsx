import { Check, WifiOff } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

type ReconnectState = "disconnected" | "reconnecting" | "reconnected";

const COPY: Record<ReconnectState, Readonly<{ title: string; description: string }>> = {
  disconnected: {
    title: "Connection lost.",
    description: "Saved content remains available.",
  },
  reconnecting: {
    title: "Reconnecting…",
    description: "Saved content remains available while the connection recovers.",
  },
  reconnected: {
    title: "Connection restored.",
    description: "Live updates are available again.",
  },
};

export function ReconnectBanner({ state }: Readonly<{ state: ReconnectState }>) {
  const copy = COPY[state];

  const Icon = state === "reconnected" ? Check : WifiOff;

  // One quiet line rather than a bordered card: the problem is informational
  // (saved content stays readable), so it should not outweigh the thread. The
  // icon is decorative; the words carry the state.
  return (
    <Alert className="flex flex-wrap items-center gap-x-2 gap-y-0 border-0 bg-transparent p-0 text-xs text-muted-foreground">
      <Icon aria-hidden="true" className="size-3.5 shrink-0" />
      <AlertTitle className="font-medium text-foreground">{copy.title}</AlertTitle>
      <AlertDescription className="text-xs">{copy.description}</AlertDescription>
    </Alert>
  );
}
