import { expect } from '@playwright/test'
import { waitForApiResponse } from '../helpers/api'
import { BasePage } from './BasePage'

export class AuthPage extends BasePage {
  readonly emailInput = this.page.getByLabel(/אימייל|Email/i)
  readonly passwordInput = this.page.getByLabel(/^סיסמה$|^Password$/i)

  async gotoRegister() {
    await this.goto('/register')
    await expect(this.heading(/יצירת חשבון|Create your account/i)).toBeVisible()
  }

  async gotoLogin() {
    await this.goto('/login')
    await expect(this.page.getByRole('button', { name: /התחברות|Sign in/i })).toBeVisible()
  }

  async register(email: string, password: string) {
    await this.gotoRegister()
    await this.emailInput.fill(email)
    await this.passwordInput.fill(password)
    const registerResponse = waitForApiResponse(this.page, /\/auth\/register/, {
      method: 'POST',
      status: 201,
    })
    await this.page.getByRole('button', { name: /יצירת חשבון|Create account/i }).click()
    await registerResponse
  }

  async login(email: string, password: string) {
    await this.gotoLogin()
    await this.emailInput.fill(email)
    await this.passwordInput.fill(password)
    const loginResponse = waitForApiResponse(this.page, /\/auth\/login/, {
      method: 'POST',
      status: 200,
    })
    await this.page.getByRole('button', { name: /התחברות|Sign in/i }).click()
    await loginResponse
  }

  async signOut() {
    await this.page.getByRole('button', { name: /התנתקות|Sign out/i }).click()
    await expect(this.page.getByRole('button', { name: /התחברות|Sign in/i })).toBeVisible()
  }
}
