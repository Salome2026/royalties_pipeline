import { randomBytes, scryptSync } from "crypto";

const password = process.argv[2];

if (!password) {
  console.error("Uso: node scripts/hash_password.mjs \"password\"");
  process.exit(1);
}

const salt = randomBytes(16).toString("base64url");
const hash = scryptSync(password, salt, 32).toString("base64url");

console.log(`scrypt$${salt}$${hash}`);
