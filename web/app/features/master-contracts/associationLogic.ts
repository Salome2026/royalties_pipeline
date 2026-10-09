export type AssociationChoice = { key: string; included: boolean; evidence_signature: string };
export type Association = AssociationChoice & {
  kind: string; code: string; source: string; account: string; titles: string[]; artists: string[];
  isrcs: string[]; automatic: boolean; status: string; selectable: boolean; reason: string;
  requires_review?: boolean;
};
export type AssociationValidation = { loading: boolean; pending: number; error: string };

export function associationScope(key: string): string {
  const values = JSON.parse(key) as string[];
  return JSON.stringify(values[0] === "TRACK" ? values : values.slice(0, 2));
}

export function associationState(item: Association, choices: AssociationChoice[]) {
  const scoped = choices.filter((value) => associationScope(value.key) === associationScope(item.key));
  const choice = scoped.find((value) => !value.included) || scoped.find((value) => value.key === item.key);
  if (choice && !choice.included) return { included: false, status: "excluded", pending: false };
  if (choice) {
    const valid = item.selectable && choice.evidence_signature === item.evidence_signature;
    return { included: valid, status: valid ? "confirmed" : "pending", pending: !valid };
  }
  if (item.automatic && item.selectable) return { included: true, status: "automatic", pending: false };
  return { included: false, status: item.selectable ? "pending" : "blocked", pending: item.selectable || !!item.requires_review };
}

export function pendingAssociationCodes(items: Association[], choices: AssociationChoice[]): string[] {
  const codes = items.filter((item) => associationState(item, choices).pending).map((item) => item.code);
  const known = new Set(items.map((item) => item.key));
  for (const choice of choices) {
    if (choice.included && !known.has(choice.key)) codes.push((JSON.parse(choice.key) as string[])[1]);
  }
  return [...new Set(codes)].sort();
}
