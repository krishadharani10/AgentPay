import type { RazorpayCheckoutOptions } from '../types'

declare global {
  interface Window {
    Razorpay?: new (options: RazorpayCheckoutOptions) => {
      open: () => void
      on: (event: string, callback: (response: unknown) => void) => void
      close: () => void
    }
  }
}

let sdkPromise: Promise<boolean> | null = null

/**
 * Dynamically loads the Razorpay Standard Checkout JS SDK script into document head.
 */
export function loadRazorpaySDK(): Promise<boolean> {
  if (typeof window === 'undefined') return Promise.resolve(false)

  if (window.Razorpay) {
    return Promise.resolve(true)
  }

  if (sdkPromise) {
    return sdkPromise
  }

  sdkPromise = new Promise((resolve) => {
    const script = document.createElement('script')
    script.src = 'https://checkout.razorpay.com/v1/checkout.js'
    script.async = true
    script.onload = () => {
      resolve(true)
    }
    script.onerror = () => {
      console.error('Failed to load Razorpay Checkout SDK script from checkout.razorpay.com')
      resolve(false)
    }
    document.body.appendChild(script)
  })

  return sdkPromise
}

export interface LaunchRazorpayParams {
  keyId: string
  amountInRupees: number
  currency?: string
  orderId?: string
  merchantName?: string
  description?: string
  prefill?: {
    name?: string
    email?: string
    contact?: string
  }
  notes?: Record<string, string>
  onSuccess: (response: {
    razorpay_payment_id: string
    razorpay_order_id: string
    razorpay_signature: string
  }) => void
  onDismiss?: () => void
  onError?: (err: Error) => void
}

/**
 * Initializes and displays the Razorpay Checkout standard popup modal.
 */
export async function launchRazorpayCheckout({
  keyId,
  amountInRupees,
  currency = 'INR',
  orderId,
  merchantName = 'AgentPay Autonomous Payment',
  description = 'AgentPay Permissioned Transaction',
  prefill = {
    name: 'AgentPay User',
    email: 'agent@agentpay.finance',
    contact: '+919876543210',
  },
  notes = {},
  onSuccess,
  onDismiss,
  onError,
}: LaunchRazorpayParams): Promise<void> {
  const isLoaded = await loadRazorpaySDK()
  if (!isLoaded || !window.Razorpay) {
    const error = new Error('Razorpay SDK could not be loaded. Please check your internet connection.')
    if (onError) onError(error)
    else alert(error.message)
    return
  }

  const options: RazorpayCheckoutOptions = {
    key: keyId,
    amount: Math.round(amountInRupees * 100), // paise
    currency: currency.toUpperCase(),
    name: merchantName,
    description: description,
    image: 'https://cdn-icons-png.flaticon.com/512/9334/9334582.png',
    order_id: orderId || undefined,
    prefill: {
      name: prefill.name || 'AgentPay User',
      email: prefill.email || 'agent@agentpay.finance',
      contact: prefill.contact || '+919876543210',
    },
    notes: {
      platform: 'AgentPay',
      ...notes,
    },
    theme: {
      color: '#4f46e5', // Indigo-600
    },
    modal: {
      ondismiss: () => {
        if (onDismiss) onDismiss()
      },
      escape: true,
      confirm_close: false,
    },
    handler: (response) => {
      onSuccess(response)
    },
  }

  try {
    const rzp = new window.Razorpay(options)
    rzp.open()
  } catch (err: unknown) {
    const error = err instanceof Error ? err : new Error(String(err))
    if (onError) onError(error)
    else console.error('Error opening Razorpay modal:', error)
  }
}
