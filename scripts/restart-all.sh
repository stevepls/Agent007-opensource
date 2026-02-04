#!/bin/bash
# Restart all Agent007 services

echo "🔄 Restarting all Agent007 services..."

# Restart Orchestrator API
echo ""
echo "=== Orchestrator API ==="
/home/steve/Agent007/Orchestrator/scripts/restart.sh

# Restart Dashboard
echo ""
echo "=== Dashboard ==="
pkill -f "next dev" 2>/dev/null || true
sleep 2
cd /home/steve/Agent007/dashboard
rm -rf .next 2>/dev/null
PORT=3004 npm run dev > /tmp/dashboard.log 2>&1 &
sleep 10

if curl -s http://localhost:3004 > /dev/null 2>&1; then
    echo "✅ Dashboard running on port 3004"
else
    echo "❌ Dashboard failed to start"
fi

echo ""
echo "=== Status ==="
curl -s http://localhost:8502/health > /dev/null && echo "✅ API: http://localhost:8502"
curl -s http://localhost:3004 > /dev/null && echo "✅ Dashboard: http://localhost:3004"
