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

  return (
    <Alert>
      <AlertTitle>{copy.title}</AlertTitle>
      <AlertDescription>{copy.description}</AlertDescription>
    </Alert>
  );
}
