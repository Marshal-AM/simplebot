const express = require("express");
const cors = require("cors");
const axios = require("axios");
const { spawn } = require("child_process");
const path = require("path");
require("dotenv").config();

const app = express();
const PORT = 3000;

app.use(cors());
app.use(express.json());
app.use(express.static("."));

// Serve video file
app.get("/video/:filename", (req, res) => {
  const filename = req.params.filename;
  const videoPath = path.join(__dirname, filename);
  res.sendFile(videoPath);
});

const DAILY_API_KEY = process.env.DAILY_API_KEY;
const DAILY_API_URL = "https://api.daily.co/v1";

if (!DAILY_API_KEY) {
  console.error("Error: DAILY_API_KEY not found in .env file");
  process.exit(1);
}

// Store active bot processes
const activeBots = new Map();

// Store current room info
let currentRoomInfo = null;

// Create a Daily room
app.post("/api/create-room", async (req, res) => {
  try {
    const response = await axios.post(
      `${DAILY_API_URL}/rooms`,
      {
        properties: {
          enable_prejoin_ui: false,
          enable_chat: true,
          enable_knocking: false,
          enable_screenshare: true,
          enable_recording: false,
        },
      },
      {
        headers: {
          Authorization: `Bearer ${DAILY_API_KEY}`,
          "Content-Type": "application/json",
        },
      }
    );

    res.json({
      url: response.data.url,
      name: response.data.name,
      id: response.data.id,
    });
  } catch (error) {
    console.error(
      "Error creating room:",
      error.response?.data || error.message
    );
    res
      .status(500)
      .json({ error: "Failed to create room", details: error.message });
  }
});

// Start bot to join room and play video
app.post("/api/start-bot", async (req, res) => {
  try {
    const { roomUrl } = req.body;

    if (!roomUrl) {
      return res.status(400).json({ error: "roomUrl is required" });
    }

    // Check if bot is already running for this room
    if (activeBots.has(roomUrl)) {
      return res.json({ message: "Bot is already running for this room" });
    }

    // Get room token for bot
    const roomName = roomUrl.split("/").pop();
    let tokenResponse;
    try {
      tokenResponse = await axios.post(
        `${DAILY_API_URL}/meeting-tokens`,
        {
          properties: {
            room_name: roomName,
            is_owner: false,
          },
        },
        {
          headers: {
            Authorization: `Bearer ${DAILY_API_KEY}`,
            "Content-Type": "application/json",
          },
        }
      );
    } catch (error) {
      console.log("Could not create token, using room URL directly");
    }

    const token = tokenResponse?.data?.token;

    // Start Python bot script
    const videoPath = path.join(__dirname, "AgenticBrowserEngine.mov");
    const botScript = path.join(__dirname, "bot.py");

    const botProcess = spawn(
      "python",
      [botScript, roomUrl, token || "", videoPath],
      {
        stdio: "inherit",
        shell: true,
      }
    );

    activeBots.set(roomUrl, botProcess);

    botProcess.on("exit", (code) => {
      activeBots.delete(roomUrl);
      console.log(`Bot process exited with code ${code}`);
    });

    botProcess.on("error", (error) => {
      activeBots.delete(roomUrl);
      console.error("Bot process error:", error);
    });

    res.json({ message: "Bot started successfully" });
  } catch (error) {
    console.error("Error starting bot:", error);
    res
      .status(500)
      .json({ error: "Failed to start bot", details: error.message });
  }
});

// Get current room info
app.get("/api/room-info", (req, res) => {
  if (currentRoomInfo) {
    res.json(currentRoomInfo);
  } else {
    res.status(404).json({ error: "No room created yet" });
  }
});

// Stop bot
app.post("/api/stop-bot", async (req, res) => {
  try {
    const { roomUrl } = req.body;

    if (!roomUrl) {
      return res.status(400).json({ error: "roomUrl is required" });
    }

    const botProcess = activeBots.get(roomUrl);
    if (botProcess) {
      botProcess.kill();
      activeBots.delete(roomUrl);
      res.json({ message: "Bot stopped successfully" });
    } else {
      res.json({ message: "No bot running for this room" });
    }
  } catch (error) {
    console.error("Error stopping bot:", error);
    res
      .status(500)
      .json({ error: "Failed to stop bot", details: error.message });
  }
});

// Function to create room and start bot automatically
async function initializeRoom() {
  try {
    console.log("\n" + "=".repeat(60));
    console.log("Creating Daily room and starting bot...");
    console.log("=".repeat(60) + "\n");

    // Create room
    const roomResponse = await axios.post(
      `${DAILY_API_URL}/rooms`,
      {
        properties: {
          enable_prejoin_ui: false,
          enable_chat: true,
          enable_knocking: false,
          enable_screenshare: true,
          enable_recording: false,
        },
      },
      {
        headers: {
          Authorization: `Bearer ${DAILY_API_KEY}`,
          "Content-Type": "application/json",
        },
      }
    );

    const roomUrl = roomResponse.data.url;
    const roomName = roomResponse.data.name;

    console.log("✅ Room created successfully!");
    console.log("\n" + "=".repeat(70));
    console.log("🎥 DAILY ROOM URL - CLICK TO JOIN:");
    console.log("=".repeat(70));
    console.log("");
    console.log("   " + roomUrl);
    console.log("");
    console.log("=".repeat(70));
    console.log("\n📋 Instructions:");
    console.log(
      "   1. Click the URL above to open the Daily room in your browser"
    );
    console.log(
      "   2. The bot will join automatically and start playing the video"
    );
    console.log("   3. You should see the video playing in the room");
    console.log("\n🤖 Starting bot in 2 seconds...\n");

    // Get room token for bot
    let token;
    try {
      const tokenResponse = await axios.post(
        `${DAILY_API_URL}/meeting-tokens`,
        {
          properties: {
            room_name: roomName,
            is_owner: false,
          },
        },
        {
          headers: {
            Authorization: `Bearer ${DAILY_API_KEY}`,
            "Content-Type": "application/json",
          },
        }
      );
      token = tokenResponse.data.token;
    } catch (error) {
      console.log("⚠️  Could not create token, using room URL directly");
      token = "";
    }

    // Wait a moment before starting bot
    await new Promise((resolve) => setTimeout(resolve, 2000));

    // Start bot
    const videoPath = path.join(__dirname, "AgenticBrowserEngine.mov");
    const botScript = path.join(__dirname, "bot.py");

    console.log("🚀 Starting bot...\n");

    const botProcess = spawn(
      "python",
      [botScript, roomUrl, token || "", videoPath],
      {
        stdio: "inherit",
        shell: true,
      }
    );

    activeBots.set(roomUrl, botProcess);

    botProcess.on("exit", (code) => {
      activeBots.delete(roomUrl);
      console.log(`\n⚠️  Bot process exited with code ${code}`);
    });

    botProcess.on("error", (error) => {
      activeBots.delete(roomUrl);
      console.error("\n❌ Bot process error:", error);
    });

    // Store room info globally for API access
    currentRoomInfo = {
      url: roomUrl,
      name: roomName,
      id: roomResponse.data.id,
    };
  } catch (error) {
    console.error(
      "\n❌ Error initializing room:",
      error.response?.data || error.message
    );
  }
}

app.listen(PORT, async () => {
  console.log(`\n🌐 Server running on http://localhost:${PORT}`);
  console.log(
    `\n📦 Make sure you have Python installed and playwright package installed`
  );

  // Automatically create room and start bot on startup
  await initializeRoom();
});
