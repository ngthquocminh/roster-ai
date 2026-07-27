import { useEffect, useRef } from "react";
import {
  Link,
  useLocation,
  useNavigate,
  useParams,
} from "react-router";

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ScenarioVersionContext } from "@/features/scenario-workspace/ScenarioVersionContext";
import { useScenarioContext } from "@/hooks/useScenarioContext";
import { getErrorStatus, USER_ERROR_COPY } from "@/lib/errors";


export function ScenarioWorkspace() {
  const { scenarioId = "" } = useParams();
  const query = useScenarioContext(scenarioId);
  const location = useLocation();
  const navigate = useNavigate();
  const terminalHeadingRef = useRef<HTMLHeadingElement>(null);
  const errorStatus = getErrorStatus(query.error);

  useEffect(() => {
    if (!query.data) {
      terminalHeadingRef.current?.focus();
    }
  }, [query.data, query.isError, query.isPending]);

  useEffect(() => {
    if (errorStatus === 401) {
      void navigate("/signin", {
        replace: true,
        state: { from: location.pathname + location.search },
      });
    }
  }, [errorStatus, location.pathname, location.search, navigate]);

  if (errorStatus === 401) {
    return null;
  }

  if (query.isPending) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-8">
        <h1
          className="text-2xl font-semibold outline-none"
          ref={terminalHeadingRef}
          tabIndex={-1}
        >
          Scenario workspace
        </h1>
        <p
          aria-live="polite"
          className="mt-3 text-sm text-muted-foreground"
        >
          Loading scenario context…
        </p>
      </main>
    );
  }

  if (query.isError && errorStatus === 404) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <h1
          className="text-2xl font-semibold outline-none"
          ref={terminalHeadingRef}
          tabIndex={-1}
        >
          Scenario not found
        </h1>
        <p className="mt-3 text-sm text-muted-foreground">
          The requested scenario is not available.
        </p>
        <Link
          className="mt-5 inline-flex min-h-11 items-center rounded-lg border px-3 text-sm font-medium outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
          to="/"
        >
          Return to catalogue
        </Link>
      </main>
    );
  }

  if (query.isError || !query.data) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <h1
          className="text-2xl font-semibold outline-none"
          ref={terminalHeadingRef}
          tabIndex={-1}
        >
          Scenario workspace
        </h1>
        <Alert className="mt-5 border-destructive/40">
          <AlertTitle>{USER_ERROR_COPY.connection.title}</AlertTitle>
          <AlertDescription>
            <p>{USER_ERROR_COPY.connection.description}</p>
            <Button
              className="mt-3 min-h-11"
              onClick={() => {
                void query.refetch();
              }}
              type="button"
              variant="outline"
            >
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <ScenarioVersionContext context={query.data} />
      <section
        aria-labelledby="scenario-data-placeholder"
        className="mt-6 rounded-lg border border-dashed p-6"
      >
        <h2 className="text-lg font-medium" id="scenario-data-placeholder">
          Scenario Data
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Scenario Data will be available in this workspace.
        </p>
      </section>
    </main>
  );
}
