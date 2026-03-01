# Deploying CoPaw to Render

This guide explains how to deploy CoPaw to [Render](https://render.com), a cloud platform that offers free and paid hosting options.

## Prerequisites

1. A [Render account](https://dashboard.render.com/register)
2. A GitHub account with this forked repository
3. An API key for your LLM provider (e.g., DashScope, OpenAI)

## Quick Deploy

### Option 1: One-Click Deploy (Recommended)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/YOUR_USERNAME/CoPaw)

1. Fork this repository to your GitHub account
2. Click the "Deploy to Render" button above (update the URL with your fork)
3. Configure environment variables in the Render dashboard
4. Deploy!

### Option 2: Manual Setup via Dashboard

1. **Fork and Push**: Fork this repository to your GitHub account

2. **Create a New Web Service**:
   - Go to [Render Dashboard](https://dashboard.render.com)
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Select the CoPaw repository

3. **Configure the Service**:
   - **Name**: `copaw` (or your preferred name)
   - **Region**: Choose the closest to your users
   - **Branch**: `main`
   - **Runtime**: Docker
   - **Dockerfile Path**: `./Dockerfile.render`
   - **Plan**: Starter (free) or Standard (recommended)

4. **Set Environment Variables**:
   | Variable | Description | Required |
   |----------|-------------|----------|
   | `DASHSCOPE_API_KEY` | DashScope API key | Yes (or OpenAI) |
   | `OPENAI_API_KEY` | OpenAI API key | Yes (or DashScope) |
   | `COPAW_ENABLED_CHANNELS` | Enabled channels | No (default: console) |
   | `COPAW_WORKING_DIR` | Working directory | No (default: /app/working) |

5. **Add Persistent Disk** (Recommended):
   - Scroll to "Disks" section
   - Click "Add Disk"
   - **Name**: `copaw-data`
   - **Mount Path**: `/app/working`
   - **Size**: 1GB minimum

6. **Deploy**: Click "Create Web Service"

### Option 3: Using render.yaml (Infrastructure as Code)

1. Fork this repository
2. Update `render.yaml` with your preferred settings
3. In Render Dashboard:
   - Go to "Blueprints"
   - Click "New Blueprint Instance"
   - Connect your repository
   - Render will automatically create services defined in `render.yaml`

## Environment Variables

### Required Variables

```bash
# At least one LLM API key is required
DASHSCOPE_API_KEY=your_dashscope_key
# OR
OPENAI_API_KEY=your_openai_key
```

### Optional Variables

```bash
# Enable specific channels (comma-separated)
COPAW_ENABLED_CHANNELS=console,dingtalk,feishu

# Custom working directory
COPAW_WORKING_DIR=/app/working

# Node environment
NODE_ENV=production
```

### Channel Configuration

For DingTalk, Feishu, or other channels, add their respective credentials:

```bash
# DingTalk
DINGTALK_CLIENT_ID=your_client_id
DINGTALK_CLIENT_SECRET=your_client_secret

# Feishu
FEISHU_APP_ID=your_app_id
FEISHU_APP_SECRET=your_app_secret
```

## Persistent Storage

Render's filesystem is ephemeral. To persist your data between deploys:

1. **Use Render Disks**: Add a persistent disk as shown above
2. **Mount Path**: Must match `COPAW_WORKING_DIR` (default: `/app/working`)
3. **Data Stored**: Config, memory, skills, and agent data

## Cost Estimation

| Plan | Specs | Monthly Cost |
|------|-------|--------------|
| Starter | 0.5 CPU, 512MB RAM | Free |
| Standard | 1 CPU, 2GB RAM | $7/month |
| Pro | 2+ CPU, 4GB+ RAM | $25+/month |
| Disk Storage | 1GB | Free |

**Recommended**: Standard plan with 1GB disk for production use.

## Troubleshooting

### Application won't start

1. Check logs in Render Dashboard → "Logs" tab
2. Ensure at least one LLM API key is set
3. Verify the PORT environment variable (Render sets this automatically)

### Data lost after deploy

1. Ensure you've added a persistent disk
2. Check mount path matches `COPAW_WORKING_DIR`

### Health check failures

1. Increase `start_period` in health check
2. Check if the application is listening on the correct port

### Out of memory

1. Upgrade to a larger plan
2. Reduce worker count if applicable

## Custom Domain (Optional)

1. Go to your service in Render Dashboard
2. Click "Settings" → "Custom Domains"
3. Add your domain and configure DNS

## Monitoring & Logs

- **Logs**: View real-time logs in Render Dashboard
- **Metrics**: CPU, memory, and network metrics available
- **Alerts**: Configure alerts for service health

## Security Considerations

1. **Never commit API keys** to your repository
2. Use Render's **Secret Files** for sensitive configuration
3. Set **COPAW_ENABLED_CHANNELS** to only what you need
4. Consider using a **private repository** for your fork

## Updating

1. Push changes to your GitHub repository
2. Render automatically redeploys on push
3. Or manually trigger redeploy in Dashboard

## Support

- [Render Documentation](https://render.com/docs)
- [CoPaw Documentation](https://copaw.agentscope.io)
- [GitHub Issues](https://github.com/agentscope-ai/CoPaw/issues)
