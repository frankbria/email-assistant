import { betterAuth } from 'better-auth'
import { APIError, createAuthMiddleware } from 'better-auth/api'
import { mongodbAdapter } from 'better-auth/adapters/mongodb'
import { nextCookies } from 'better-auth/next-js'
import { MongoClient } from 'mongodb'

export const mongoClient = new MongoClient(process.env.MONGODB_URI ?? 'mongodb://localhost:27017')
export const authDb = mongoClient.db(process.env.MONGODB_DB ?? 'email_assistant')

// Single-owner app: the first account is the owner.
export async function ownerExists(): Promise<boolean> {
  return (await authDb.collection('user').countDocuments({}, { limit: 1 })) > 0
}

export const auth = betterAuth({
  database: mongodbAdapter(authDb),
  emailAndPassword: { enabled: true },
  user: {
    additionalFields: {
      // Every account is the owner. The unique index on this field (below) makes a
      // second owner impossible even when two sign-ups race past the check.
      role: { type: 'string', defaultValue: 'owner', input: false },
    },
  },
  hooks: {
    // Request-level, so a closed sign-up is refused before the password is hashed.
    before: createAuthMiddleware(async (context) => {
      if (context.path !== '/sign-up/email') return
      await authDb.collection('user').createIndex({ role: 1 }, { unique: true })
      if (await ownerExists()) {
        throw new APIError('FORBIDDEN', { message: 'Sign-up is closed: this app already has an owner.' })
      }
    }),
  },
  plugins: [nextCookies()],
})
