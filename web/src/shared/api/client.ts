export class HttpError extends Error {
  constructor(
    public status: number,
    url: string,
  ) {
    super(status === 404 ? `${url} was not found. Run make report, then reload.` : `${url} answered ${status}.`);
  }
}

export async function fetchJSON<T>(url: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(url, { signal });
  if (!r.ok) throw new HttpError(r.status, url);
  return (await r.json()) as T;
}

export const base = import.meta.env.VITE_DATA_URL ?? "/data";
