using MarketMind.Api;

// Entry point only — compose services, wire CORS for the Vite frontend, map the routes, run.
var builder = WebApplication.CreateBuilder(args);

builder.Services.AddMarketMind();
builder.Services.AddCors(o => o.AddDefaultPolicy(p => p.AllowAnyOrigin().AllowAnyHeader().AllowAnyMethod()));

var app = builder.Build();
app.UseCors();
app.MapMarketMind();
app.Run();
