import express from "express";
import multer from "multer";
import fs from "fs";
import OpenAI from "openai";

const router = express.Router();

const upload = multer({
  dest: "uploads/",
});

router.post("/analyze-image", upload.single("image"), async (req, res) => {
  try {

    // ✅ OpenRouter Configuration
    const openai = new OpenAI({
      apiKey: process.env.OPENAI_API_KEY, // your sk-or-v1 key
      baseURL: "https://openrouter.ai/api/v1",
      defaultHeaders: {
        "HTTP-Referer": "http://localhost:6000",
        "X-Title": "Image Analyzer App",
      },
    });

    if (!req.file) {
      return res.status(400).json({
        status: "error",
        message: "No image uploaded",
      });
    }

    const imagePath = req.file.path;
    const imageBuffer = fs.readFileSync(imagePath);
    const base64Image = imageBuffer.toString("base64");

    const response = await openai.chat.completions.create({
      model: "openai/gpt-4o-mini",
      messages: [
        {
          role: "user",
          content: [
            {
              type: "text",
              text: "Analyze this image in full detail.",
            },
            {
              type: "image_url",
              image_url: {
                url: `data:image/jpeg;base64,${base64Image}`,
              },
            },
          ],
        },
      ],
      max_tokens: 1000,
    });

    fs.unlinkSync(imagePath);

    res.json({
      status: "success",
      analysis: response.choices[0].message.content,
    });

  } catch (error) {
    console.error(error.response?.data || error);
    res.status(500).json({
      status: "error",
      message: "Image analysis failed",
    });
  }
});

export default router;
