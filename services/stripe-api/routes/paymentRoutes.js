// paymentRoute.js
import express from "express";
import stripe from "../utils/stripe.js";

const router = express.Router();

// ✅ Create PaymentIntent
router.post("/create-payment-intent", async (req, res) => {
  try {
    const { amount, currency = "inr", customer_email } = req.body;

    const paymentIntent = await stripe.paymentIntents.create({
      amount,
      currency,
      automatic_payment_methods: {
        enabled: true, // 🔁 Handles 3DS automatically
      },
      receipt_email: customer_email,
    });

    return res.status(200).json({
      clientSecret: paymentIntent.client_secret,
    });
  } catch (error) {
    return res.status(500).json({
      status: "error",
      message: "Failed to create PaymentIntent.",
      error: error.message,
    });
  }
});

export default router;
