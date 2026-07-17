import express from "express";

const app = express();

export class UsersController {
  list() {
    return prisma.user.findMany();
  }
}

app.get("/users", listUsers);

export function listUsers() {
  return [];
}
