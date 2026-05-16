import { NextResponse } from "next/server";
import { currentUser } from "../_auth";

export async function GET() {
  const user = await currentUser();
  return NextResponse.json({ authenticated: Boolean(user), user });
}
