import { useEffect, useState } from "react";
import { onConnection } from "../lib/api.js";

// "connecting" until the first request answers, then whatever api() last reported.
export function useConnection() {
  const [state, setState] = useState("connecting");
  useEffect(() => onConnection(setState), []);
  return state;
}
