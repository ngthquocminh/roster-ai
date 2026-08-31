import { Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

const COPY_FAILURE = "Copy unavailable. Select the identifier to copy it manually.";
const ANNOUNCEMENT_DURATION_MS = 2_000;

export function IdentifierCopyButton({
  identifierType,
  value,
}: Readonly<{ value: string; identifierType: string }>) {
  const [announcement, setAnnouncement] = useState("");
  const clearTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(
    () => () => {
      if (clearTimer.current !== undefined) clearTimeout(clearTimer.current);
    },
    [],
  );

  const announce = (message: string) => {
    if (clearTimer.current !== undefined) clearTimeout(clearTimer.current);
    setAnnouncement(message);
    clearTimer.current = setTimeout(() => setAnnouncement(""), ANNOUNCEMENT_DURATION_MS);
  };

  const copy = async () => {
    try {
      if (!navigator.clipboard) throw new Error("Clipboard API unavailable");
      await navigator.clipboard.writeText(value);
      announce(`Copied ${identifierType}`);
    } catch {
      announce(COPY_FAILURE);
    }
  };

  return (
    <span className="inline-flex min-w-0 max-w-full items-center gap-1.5">
      <span className="min-w-0 break-all font-mono text-xs" title={value}>{value}</span>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              aria-label={`Copy ${identifierType} ${value}`}
              className="min-h-11 min-w-11"
              onClick={() => { void copy(); }}
              size="icon"
              type="button"
              variant="ghost"
            >
              <Copy aria-hidden="true" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Copy {identifierType}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <span aria-live="polite" className="sr-only" role="status">{announcement}</span>
    </span>
  );
}
