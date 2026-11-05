/** Same narrow official-source URL policy as the backend presentation layer. */
const HOSTS = new Set(["gob.mx", "www.gob.mx", "www.sct.gob.mx", "www.transtats.bts.gov", "transtats.bts.gov", "www.bts.gov", "bts.gov", "data.transportation.gov"]);
export function officialRouteSourceUrl(raw: string): string | undefined {
  try {
    const url = new URL(raw);
    if (url.protocol !== "https:" || !HOSTS.has(url.hostname) || url.username || url.password || url.port || url.hash) return undefined;
    if (url.search) {
      if (!["www.transtats.bts.gov", "transtats.bts.gov"].includes(url.hostname) || url.pathname !== "/DL_SelectFields.aspx") return undefined;
      const params = url.searchParams;
      if (params.size !== 4 || params.get("gnoyr_VQ") !== "FJE" || params.get("QO_fu146_anzr") !== "Nv4 Pn44vr45" ||
          params.get("requested_geography") !== "Mexico" || !/^20\d{2}$/.test(params.get("requested_year") ?? "")) return undefined;
    }
    return url.href;
  } catch { return undefined; }
}
