import { useState, useEffect } from 'react';
import { generateCodeChallenge, generateCodeVerifier } from '../utils/pkce';

const AUTH_URL = process.env.REACT_APP_AUTH_URL || 'https://localhost';
const KC_URL = process.env.REACT_APP_KEYCLOAK_URL;
const KC_REALM = process.env.REACT_APP_KEYCLOAK_REALM;
const KC_CLIENT = process.env.REACT_APP_KEYCLOAK_CLIENT_ID;

export function useAuth() {
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    let mounted = true;

    const checkAuth = async () => {
      try {
        const res = await fetch(`${AUTH_URL}/auth/status`, { credentials: 'include' });
        if (!mounted) return;
        if (!res.ok) { setAuthed(false); return; }

        const data = await res.json();
        setAuthed(data.authenticated);

        // Чистим URL после успешного возврата из Keycloak
        if (data.authenticated && window.location.search.includes('auth=')) {
          window.history.replaceState({}, '', window.location.pathname);
        }
      } catch {
        if (mounted) setAuthed(false);
      }
    };

    checkAuth();
    return () => { mounted = false; };
  }, []);

  const login = async () => {
    const verifier = generateCodeVerifier();
    const challenge = await generateCodeChallenge(verifier);
    sessionStorage.setItem('pkce_verifier', verifier);

    const params = new URLSearchParams({
      client_id: KC_CLIENT || '',
      redirect_uri: `${AUTH_URL}/auth/callback`,
      response_type: 'code',
      scope: 'openid',
      code_challenge: challenge,
      code_challenge_method: 'S256',
      state: btoa(verifier)
    });

    window.location.href = `${KC_URL}/realms/${KC_REALM}/protocol/openid-connect/auth?${params}`;
  };

  return { authed, login };
}