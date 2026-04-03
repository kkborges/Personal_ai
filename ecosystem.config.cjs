module.exports = {
  apps: [{
    name: 'personal-ai-mobile',
    script: 'python3',
    args: '-m uvicorn main:app --host 0.0.0.0 --port 8765 --log-level info',
    cwd: '/home/user/personal-ai-mobile',
    env: { PYTHONPATH: '/home/user/personal-ai-mobile', NODE_ENV: 'development' },
    watch: false,
    instances: 1,
    exec_mode: 'fork',
    max_restarts: 5,
    min_uptime: '5s',
  }]
}
