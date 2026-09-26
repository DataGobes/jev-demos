/** Shape of the `/health` payload the backend returns (see jevviz.api). */
export type HealthResponse = { simulated: boolean; model: string };

/**
 * Fetch `/health` and return whether the backend is running in demo
 * (simulated) mode, or `null` if the backend can't be reached or returns a
 * non-ok response. Never throws: the caller (App, on mount) is meant to seed
 * the SIMULATED badge before any run happens, and a backend that's merely
 * down yet is not itself an error worth surfacing.
 */
export async function fetchSimulated(): Promise<boolean | null> {
  try {
    const resp = await fetch("/health");
    if (!resp.ok) return null;
    const body = (await resp.json()) as HealthResponse;
    return Boolean(body.simulated);
  } catch {
    return null;
  }
}
