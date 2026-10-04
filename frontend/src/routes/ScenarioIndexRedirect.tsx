import { Navigate, useLocation } from "react-router";

/**
 * `/scenarios/:scenarioId` used to be the Chat tab. Chat now lives in the
 * workspace's side panel, so the index lands on Scenario Data. The search
 * string and history state are carried over: `?conversation=` opens the panel
 * on that thread, and any `evidenceOrigin` history state still reaches
 * ChatView's focus restoration.
 */
export function ScenarioIndexRedirect() {
  const location = useLocation();
  return <Navigate replace state={location.state} to={{ pathname: "data", search: location.search, hash: location.hash }} />;
}
