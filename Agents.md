# oratoria-backend

This file provides context about the project for AI assistants.

## Project Overview

- **Ecosystem**: Typescript

## Tech Stack

- **Runtime**: bun
- **Package Manager**: bun

### Backend

- Framework: hono
- Validation: zod

### Database

- Database: postgres
- ORM: prisma

### Authentication

- Provider: better-auth

### Additional Features

- Testing: vitest
- Realtime: socket-io

## Project Structure

```
oratoria-backend/
├── apps/
│   └── server/      # Backend API
├── packages/
│   ├── auth/        # Authentication
│   └── db/          # Database schema
```

## Common Commands

- `bun install` - Install dependencies
- `bun dev` - Start development server
- `bun build` - Build for production
- `bun test` - Run tests
- `bun db:push` - Push database schema
- `bun db:studio` - Open database UI

## Maintenance

Keep Agents.md updated when:

- Adding/removing dependencies
- Changing project structure
- Adding new features or services
- Modifying build/dev workflows

AI assistants should suggest updates to this file when they notice relevant changes.
