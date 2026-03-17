import dotenv from "dotenv";
dotenv.config(); // MUST BE FIRST

import express from "express";
import cors from "cors";
import admin from "firebase-admin";
import { v4 as uuidv4 } from "uuid";
import serviceAccount from "./serviceAccountKey.json" with { type: "json" };

import imageRoutes from "./routes/imageAnalyze.js";

const app = express();

app.use(cors());
app.use(express.json());

app.get("/", (_req, res) => {
  res.status(200).json({
    success: true,
    service: "image-analyze-api",
    message: "API is running",
  });
});

/* =====================================
   🔥 FIREBASE ADMIN INIT
===================================== */
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
    const { userId, fcmToken } = req.body;

    await db.collection("users").doc(userId).set(
      { fcmToken },
      { merge: true }
    );

    res.json({ success: true });
  } catch (err) {
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
