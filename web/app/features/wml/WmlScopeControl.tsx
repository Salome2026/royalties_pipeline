'use client';
import { useEffect, useState } from 'react';
import styles from './Wml.module.css';

export function selectedRoyaltyScope(): 'regular'|'wml' {
  if (typeof document === 'undefined') return 'regular';
  return document.cookie.split('; ').some((v) => v === 'vpo_royalty_scope=wml') ? 'wml' : 'regular';
}

export function WmlScopeControl({view}: {view:string}) {
  const [enabled,setEnabled] = useState(false);
  const [scope,setScope] = useState<'regular'|'wml'>('regular');
  useEffect(() => {
    setScope(selectedRoyaltyScope());
    fetch('/api/wml',{cache:'no-store'}).then((r) => r.ok ? r.json() : null).then((data) => {
      setEnabled(Boolean(data?.enabled));
      if (data && !data.enabled && selectedRoyaltyScope() === 'wml') {
        document.cookie='vpo_royalty_scope=regular; Path=/; SameSite=Lax';
        window.location.reload();
      }
    }).catch(() => setEnabled(false));
  },[view]);
  if (!['catalog','master-contracts','royalties-dashboard','royalties'].includes(view)) return null;
  return <label className={styles.scopeControl}>
    <span>Ámbito de regalías</span>
    <select value={scope} onChange={(event) => {
      const value=event.target.value === 'wml' ? 'wml' : 'regular';
      document.cookie=`vpo_royalty_scope=${value}; Path=/; SameSite=Lax`;
      window.location.reload();
    }}>
      <option value="regular">Royalties habituales</option>
      <option value="wml" disabled={!enabled}>WML · Base al 100%{enabled ? '' : ' · Desactivada'}</option>
    </select>
    {scope === 'wml' && <small>Ámbito aislado · referencias sin aplicación automática</small>}
  </label>;
}
