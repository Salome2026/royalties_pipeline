export type AssociationChoice = { key: string; included: boolean; evidence_signature: string };
export type Association = AssociationChoice & {
  kind: string; code: string; source: string; account: string; titles: string[]; artists: string[];
  isrcs: string[]; automatic: boolean; status: string; selectable: boolean; reason: string;
  requires_review?: boolean;
  reference_group?: "associated" | "ugc";
  content_origins?: string[];
};
export type AssociationGroup = { scope: string; kind: string; code: string; items: Association[]; section: "associated" | "ugc" };
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

export function groupedAssociations(items: Association[], choices: AssociationChoice[]): AssociationGroup[] {
  const groups = new Map<string, AssociationGroup>();
  const decisions = new Set(choices.map((choice) => associationScope(choice.key)));
  for (const item of items) {
    const scope = associationScope(item.key);
    let group = groups.get(scope);
    if (!group) {
      group = { scope, kind: item.kind, code: item.code, items: [], section: "ugc" };
      groups.set(scope, group);
    }
    group.items.push(item);
    // Doubts and saved decisions stay in the editable list, including future evidence changes.
    if (item.reference_group !== "ugc" || associationState(item, choices).pending || decisions.has(scope)) {
      group.section = "associated";
    }
  }
  return [...groups.values()];
}

export function associationGroupState(group: AssociationGroup, choices: AssociationChoice[]) {
  const states = group.items.map((item) => associationState(item, choices));
  const pending = states.some((state) => state.pending);
  const included = states.every((state) => state.included);
  const status = pending ? "pending" : included ? (states.every((state) => state.status === "automatic") ? "automatic" : "confirmed")
    : states.every((state) => state.status === "excluded") ? "excluded" : "blocked";
  return { included, pending, status, automatic: group.items.every((item) => item.automatic),
    selectable: group.items.every((item) => item.selectable) };
}
