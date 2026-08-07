import { useEffect, useState } from "react";

const PHONE_QUERY = "(max-width: 767px)";

function matchesPhoneViewport() {
  return typeof window !== "undefined" && window.matchMedia(PHONE_QUERY).matches;
}

export function usePhoneViewport() {
  const [isPhone, setIsPhone] = useState(matchesPhoneViewport);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const query = window.matchMedia(PHONE_QUERY);
    const update = (event: MediaQueryListEvent) => setIsPhone(event.matches);
    setIsPhone(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return isPhone;
}
