/**
 * SCEN-02 criterion 2: name a scenario, pick a backend-offered fixture,
 * submit, see it appear in the list. Controlled by the parent (`Home`) via
 * `open`/`onOpenChange` so the same component instance can be triggered from
 * both "New Scenario" button locations (header + empty-state) without a
 * second dialog mount.
 *
 * Fixture selection is a Radix `Select` populated from `useFixtures()` —
 * never a text input (D-03). This is the entire reason v0.4 has no path for
 * introducing new input files: the fixtures the backend already has are the
 * whole universe of valid values, so a free-text field could only ever name
 * something that cannot exist.
 *
 * Every UI-SPEC state (01-UI-SPEC.md E2/E3) is handled here:
 *   - empty:    unfilled form is the default open state, submit disabled.
 *   - partial:  submit stays disabled until name is non-empty AND a fixture
 *               is chosen — no submit-then-reject round trip for a condition
 *               knowable client-side (server remains the source of truth;
 *               ASVS V5 — the 422 branch below still exists and still
 *               renders, because "unreachable through this UI" is a claim
 *               about today's client, not the server's contract).
 *   - loading:  submit shows a spinner and disables; the name input and the
 *               Select ALSO disable — disabling only the button would leave
 *               the form editable mid-flight, so the eventual scenario would
 *               not match what the form displayed at submit time.
 *   - error:    branches on the rejected error's `status`, not its message
 *               text (T-1-02) — 400 (unknown fixture) renders under the
 *               Select, 422 (validation) renders under the name field. The
 *               dialog stays open and in-progress input is preserved.
 * Fixture states mirror the same shape one level down (loading/empty/error
 * placeholders on the Select itself), per UI-SPEC E3.
 *
 * No optimistic update, and no invented client-side uniqueness rule: two
 * submissions with identical name+fixture are two legitimately distinct
 * scenarios, because the backend enforces no uniqueness.
 */
import * as React from "react";
import { LoaderCircle } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useFixtures } from "@/hooks/useFixtures";
import { useCreateScenario } from "@/hooks/useCreateScenario";

interface CreateScenarioDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function fixtureSelectPlaceholder(
  fixturesLoading: boolean,
  fixturesEmpty: boolean,
): string | undefined {
  if (fixturesLoading) return "Loading fixtures…";
  if (fixturesEmpty) return "No fixtures available";
  return undefined;
}

export function CreateScenarioDialog({
  open,
  onOpenChange,
}: CreateScenarioDialogProps) {
  const [name, setName] = React.useState("");
  const [fixture, setFixture] = React.useState("");

  const fixturesQuery = useFixtures();
  const createScenario = useCreateScenario();

  // The unfilled form is the modal's default state (E2/empty) — reset on
  // every close so the NEXT open never inherits a prior attempt's input or
  // error, whether that attempt succeeded or was abandoned mid-way.
  React.useEffect(() => {
    if (!open) {
      setName("");
      setFixture("");
      createScenario.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const fixtures = fixturesQuery.data ?? [];
  const fixturesLoading = fixturesQuery.isLoading;
  const fixturesEmpty =
    !fixturesLoading && !fixturesQuery.isError && fixtures.length === 0;
  const fixturesUnusable = fixturesLoading || fixturesEmpty || fixturesQuery.isError;

  const isSubmitting = createScenario.isPending;
  const canSubmit = name.trim().length > 0 && fixture.length > 0 && !isSubmitting;

  const submitError = createScenario.error as { status?: number } | null;
  const fixtureErrorMessage =
    submitError?.status === 400
      ? "That fixture is no longer available on the server. Refresh the fixture list and try again."
      : undefined;
  const nameErrorMessage =
    submitError?.status === 422 ? "Name is required." : undefined;

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    // Two identical submissions are two distinct scenarios — no client-side
    // dedupe or invented uniqueness check. Each call is independent.
    createScenario.mutate(
      { name, fixture },
      {
        onSuccess: () => {
          onOpenChange(false);
        },
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="text-[20px] leading-[1.2] font-semibold">
            New Scenario
          </DialogTitle>
        </DialogHeader>
        {/* min-w-0 lets the grid/flex children shrink below their content's
            intrinsic width, so a long fixture name is clamped by the Select
            trigger instead of widening the whole dialog (UAT gap, test 4). */}
        <form onSubmit={handleSubmit} className="flex min-w-0 flex-col gap-4">
          <div
            className="flex flex-col gap-1.5"
            data-testid="scenario-name-field"
          >
            <label
              htmlFor="scenario-name"
              className="text-xs leading-[1.2] text-muted-foreground"
            >
              Name
            </label>
            <Input
              id="scenario-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={isSubmitting}
              aria-invalid={Boolean(nameErrorMessage)}
            />
            {nameErrorMessage && (
              <p className="text-xs text-destructive">{nameErrorMessage}</p>
            )}
          </div>
          <div
            className="flex min-w-0 flex-col gap-1.5"
            data-testid="scenario-fixture-field"
          >
            <label
              htmlFor="scenario-fixture"
              className="text-xs leading-[1.2] text-muted-foreground"
            >
              Fixture
            </label>
            <Select
              value={fixture}
              onValueChange={setFixture}
              disabled={fixturesUnusable || isSubmitting}
            >
              <SelectTrigger id="scenario-fixture" className="w-full min-w-0">
                <SelectValue
                  placeholder={fixtureSelectPlaceholder(
                    fixturesLoading,
                    fixturesEmpty,
                  )}
                />
              </SelectTrigger>
              <SelectContent>
                {fixtures.map((fixtureName) => (
                  <SelectItem key={fixtureName} value={fixtureName}>
                    <span className="truncate">{fixtureName}</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {fixtureErrorMessage && (
              <p className="text-xs text-destructive">{fixtureErrorMessage}</p>
            )}
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!canSubmit}>
              {isSubmitting && (
                <LoaderCircle
                  className="size-4 animate-spin"
                  aria-hidden="true"
                />
              )}
              Create Scenario
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
