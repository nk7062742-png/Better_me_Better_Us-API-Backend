import dotenv from "dotenv";
dotenv.config(); // MUST BE FIRST

import express from "express";
import cors from "cors";
import admin from "firebase-admin";
import { v4 as uuidv4 } from "uuid";
import fs from "fs";
import path from "path";

// Prefer service account from env (base64 JSON). Fallback to local file for dev.
function getServiceAccount() {
  const b64 = process.env.SERVICE_ACCOUNT_B64;
  if (b64) {
    try {
      const json = Buffer.from(b64, "base64").toString("utf8");
      return JSON.parse(json);
    } catch (e) {
      console.error("Failed to parse SERVICE_ACCOUNT_B64:", e.message);
    }
  }

  const credPath = process.env.GOOGLE_APPLICATION_CREDENTIALS;
  if (credPath && fs.existsSync(credPath)) {
    try {
      return JSON.parse(fs.readFileSync(credPath, "utf8"));
    } catch (e) {
      console.error("Failed to read GOOGLE_APPLICATION_CREDENTIALS:", e.message);
    }
  }

  const localPath = path.join(process.cwd(), "serviceAccountKey.json");
  if (fs.existsSync(localPath)) {
    return JSON.parse(fs.readFileSync(localPath, "utf8"));
  }
  throw new Error("No service account credentials provided");
}

import imageRoutes from "./routes/imageAnalyze.js";

const app = express();

app.use(cors());
app.use(express.json());

/* =====================================
   🔥 FIREBASE ADMIN INIT
===================================== */
const serviceAccount = getServiceAccount();
admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
});

const db = admin.firestore();

/* =====================================
   🧠 IMAGE ANALYZE ROUTE
===================================== */
app.use("/api", imageRoutes);

/* =====================================
   🔔 SAVE FCM TOKEN
===================================== */
app.post("/api/save-token", async (req, res) => {
  try {
    const { userId } = req.body;
    const fcmToken = req.body.fcmToken || req.body.token;

    if (!userId || !fcmToken) {
      return res.status(400).json({ error: "userId and fcmToken are required" });
    }

    console.log("[save-token] user=", userId, "tokenLen=", fcmToken.length);
    await db.collection("users").doc(userId).set(
      { fcmToken },
      { merge: true }
    );

    res.json({ success: true });
  } catch (err) {
    console.error("[save-token] error:", err);
    res.status(500).json({ error: err.message });
  }
});

/* =====================================
   💬 CREATE MEDIATION + SEND PUSH
===================================== */
app.post("/api/create-mediation", async (req, res) => {
  try {
    const { partner1Id, partner2Id, issueTitle, story } = req.body;

    const discussionId = uuidv4();

    // Save Mediation
    await db.collection("mediations").doc(discussionId).set({
      discussionId,
      partner1Id,
      partner2Id,
      issueTitle,
      story,
      status: "pending",
      createdAt: admin.firestore.FieldValue.serverTimestamp(),
    });

    // Get Partner 2 Token
    const userDoc = await db.collection("users").doc(partner2Id).get();
    const partner2Token = userDoc.data()?.fcmToken;

    if (!partner2Token) {
      return res.json({ message: "No FCM token found" });
    }

    // Send Push Notification
    await admin.messaging().send({
      token: partner2Token,
      notification: {
        title: "Mediation Invitation",
        body: issueTitle,
      },
      data: {
        type: "mediation_invite",
        discussionId,
      },
      android: {
        priority: "high",
      },
    });

    res.json({
      success: true,
      discussionId,
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

/* =====================================
   🚀 START SERVER
===================================== */
app.listen(process.env.PORT || 5000, () => {
  console.log(`Server running on port ${process.env.PORT || 5000}`);
});
