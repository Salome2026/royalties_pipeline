export function incorporatedCommissionForArtist(
  expenses: { amount: number; destination: string; artist: string }[],
  artist: string,
): number {
  return expenses.reduce((total, expense) => total + (
    expense.destination === "artist_base" && expense.artist === artist ? expense.amount : 0
  ), 0);
}

export function compositeBaseAdjustment(amount: number, equalShare: number, incorporated: number): number {
  // The saved line already contains its incorporated commission. The preview
  // adds it separately, so it must not also live in the editable adjustment.
  return amount - equalShare - incorporated;
}
