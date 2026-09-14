"use client";

import { useEffect } from "react";

export function DocRedirect({ target }: { target: string }) {
  useEffect(() => {
    window.location.replace(target + (target.includes("#") ? "" : window.location.hash));
  }, [target]);
  return <main className="editorial"><h1>Page moved</h1><a href={target}>Continue to documentation →</a></main>;
}
