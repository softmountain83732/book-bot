module.exports = {
  apps: [
    {
      name: "my-python-app",
      script: "./run.sh",
      interpreter: "/bin/bash",
      cwd: "/root/bookbot",

      autorestart: true,
      watch: false,
      max_restarts: 10,
      restart_delay: 3000,

      time: true,
      exp_backoff_restart_delay: 100
    },
    {
      name: "book-api",
      script: "python3",
      args: "-m uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --workers 2",
      cwd: "/root/bookbot",

      autorestart: true,
      watch: false,
      max_restarts: 10,
      restart_delay: 3000,

      time: true,
      exp_backoff_restart_delay: 100,
      env: {
        PORT: 8000,
        PYTHONPATH: "/root/bookbot"
      }
    }
  ]
};
