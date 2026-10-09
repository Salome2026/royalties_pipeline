const artistKey = (name: string) => name.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").trim().replace(/\s+/g, " ").toLowerCase();

export function resolveContractArtist(name: string, options: string[]): string | null {
  const key = artistKey(name);
  if (!key) return null;
  const matches = options.filter((option) => artistKey(option) === key);
  return matches.length === 1 ? matches[0] : null;
}

export function prepareContractArtists(selected: string[], input: string, options: string[]): { artists: string[]; error: string } {
  const artists = [...new Set(selected)];
  if (!input.trim()) return { artists, error: "" };
  const artist = resolveContractArtist(input, options);
  if (!artist) return { artists, error: "Elegí un nombre completo de la lista de artistas o proyectos." };
  if (artists.some((name) => artistKey(name) === artistKey(artist))) return { artists, error: "" };
  if (artists.length >= 20) return { artists, error: "Podés seleccionar hasta 20 artistas o proyectos." };
  return { artists: [...artists, artist], error: "" };
}
