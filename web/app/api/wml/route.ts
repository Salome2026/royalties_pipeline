import { NextRequest, NextResponse } from 'next/server';
import { apiConfig } from '../_auth';

async function forward(request: NextRequest, method: 'GET'|'PATCH'|'POST') {
  const config = await apiConfig(method === 'GET' ? 'viewer' : 'editor');
  if ('error' in config) return config.error;
  const isrc = request.nextUrl.searchParams.get('isrc');
  const path = isrc ? `/wml/references/${encodeURIComponent(isrc)}` : `/wml/workspace${method === 'POST' ? '/process' : ''}`;
  const response = await fetch(`${config.apiUrl}${path}`, {
    method,
    headers: {'X-VPO-API-Key': config.apiKey, 'X-VPO-Username': config.user.username,
      ...(isrc ? {'X-VPO-Royalty-Scope':'wml'} : {}),
      ...(method === 'PATCH' ? {'Content-Type':'application/json'} : {})},
    ...(method === 'PATCH' ? {body: JSON.stringify(await request.json())} : {}),
    cache:'no-store',
  });
  const body = await response.json().catch(() => ({detail:'No se pudo consultar WML.'}));
  return NextResponse.json(response.ok ? body : {error: body.detail || body.error}, {status:response.status});
}
export const GET = (request: NextRequest) => forward(request,'GET');
export const PATCH = (request: NextRequest) => forward(request,'PATCH');
export const POST = (request: NextRequest) => forward(request,'POST');
