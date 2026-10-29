import { NextRequest } from "next/server";
import { forwardExplorer } from "../_explorer";
export const maxDuration = 180;
export async function GET(request: NextRequest) { return forwardExplorer(request, "/royalties-dashboard/track"); }
