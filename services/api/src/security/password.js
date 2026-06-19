const bcrypt = require("bcrypt");

function resolveSaltRounds() {
  const parsedRounds = Number(process.env.BCRYPT_SALT_ROUNDS || 12);
  if (!Number.isInteger(parsedRounds) || parsedRounds < 10) {
    return 12;
  }
  return parsedRounds;
}

async function hashPassword(plainTextPassword) {
  return bcrypt.hash(String(plainTextPassword), resolveSaltRounds());
}

async function verifyPassword(plainTextPassword, hashedPassword) {
  return bcrypt.compare(String(plainTextPassword), String(hashedPassword));
}

module.exports = {
  hashPassword,
  verifyPassword
};
