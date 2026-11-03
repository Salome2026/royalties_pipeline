export function parseContractNumbers(value: string): { numbers: number[]; error?: string } {
  if (!value.trim()) return { numbers: [] };
  const parts = value.split(",").map((item) => item.trim()).filter(Boolean);
  if (!parts.length || parts.some((item) => !/^\d+$/.test(item) || !Number.isSafeInteger(Number(item)) || Number(item) < 10010)) {
    return { numbers: [], error: "Ingresá solo números de contrato, separados por comas." };
  }
  const numbers = [...new Set(parts.map(Number))];
  return numbers.length > 100 ? { numbers: [], error: "Podés elegir hasta 100 contratos." } : { numbers };
}
