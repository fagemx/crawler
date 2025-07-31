#!/usr/bin/env python3
"""
Docker 配置驗證腳本

快速驗證 docker-compose.yml 配置是否正確
"""

import subprocess
import sys
import yaml
from pathlib import Path


def check_docker_compose_syntax():
    """檢查 docker-compose.yml 語法"""
    print("🔍 Checking docker-compose.yml syntax...")
    
    try:
        result = subprocess.run(
            ["docker-compose", "config"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("✅ docker-compose.yml syntax is valid")
            return True
        else:
            print("❌ docker-compose.yml syntax error:")
            print(result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ docker-compose config check timed out")
        return False
    except FileNotFoundError:
        print("❌ docker-compose command not found")
        return False
    except Exception as e:
        print(f"❌ Error checking docker-compose syntax: {e}")
        return False


def check_required_files():
    """檢查必要的檔案是否存在"""
    print("\n🔍 Checking required files...")
    
    required_files = [
        "docker-compose.yml",
        "mcp_server/Dockerfile",
        "agents/vision/Dockerfile",
        "agents/playwright_crawler/Dockerfile",
        ".env.example"
    ]
    
    missing_files = []
    
    for file_path in required_files:
        full_path = Path(file_path)
        if full_path.exists():
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path} - MISSING")
            missing_files.append(file_path)
    
    return len(missing_files) == 0


def analyze_docker_compose():
    """分析 docker-compose.yml 配置"""
    print("\n🔍 Analyzing docker-compose.yml configuration...")
    
    try:
        with open("docker-compose.yml", "r", encoding="utf-8") as f:
            compose_data = yaml.safe_load(f)
        
        services = compose_data.get("services", {})
        
        # 檢查目標服務
        target_services = ["mcp-server", "vision-agent", "playwright-crawler-agent"]
        
        print(f"\n📊 Service Analysis:")
        for service_name in target_services:
            if service_name in services:
                service = services[service_name]
                print(f"\n✅ {service_name}:")
                
                # 檢查基本配置
                if "build" in service:
                    print(f"   📦 Build: {service['build']}")
                if "ports" in service:
                    print(f"   🔌 Ports: {service['ports']}")
                if "environment" in service:
                    env_count = len(service['environment'])
                    print(f"   🌍 Environment variables: {env_count}")
                if "depends_on" in service:
                    deps = list(service['depends_on'].keys())
                    print(f"   🔗 Dependencies: {deps}")
                if "healthcheck" in service:
                    print(f"   🏥 Health check: configured")
                else:
                    print(f"   ⚠️ Health check: missing")
                if "networks" in service:
                    print(f"   🌐 Networks: {service['networks']}")
                else:
                    print(f"   ⚠️ Networks: missing")
                    
            else:
                print(f"❌ {service_name}: NOT FOUND")
        
        # 檢查網路配置
        networks = compose_data.get("networks", {})
        if "social-media-network" in networks:
            print(f"\n✅ Network 'social-media-network' is configured")
        else:
            print(f"\n❌ Network 'social-media-network' is missing")
        
        return True
        
    except Exception as e:
        print(f"❌ Error analyzing docker-compose.yml: {e}")
        return False


def check_environment_variables():
    """檢查環境變數配置"""
    print("\n🔍 Checking environment variables...")
    
    required_env_vars = [
        "MCP_SERVER_URL",
        "DATABASE_URL", 
        "REDIS_URL",
        "AGENT_NAME",
        "AGENT_ROLE",
        "AGENT_PORT"
    ]
    
    # 檢查 .env.example
    env_example_path = Path(".env.example")
    if env_example_path.exists():
        print("✅ .env.example exists")
        
        try:
            with open(env_example_path, "r", encoding="utf-8") as f:
                env_content = f.read()
            
            found_vars = []
            for var in required_env_vars:
                if var in env_content:
                    found_vars.append(var)
                    print(f"   ✅ {var}")
                else:
                    print(f"   ⚠️ {var} - not found in .env.example")
            
            print(f"\n📊 Environment variables: {len(found_vars)}/{len(required_env_vars)} found")
            
        except Exception as e:
            print(f"❌ Error reading .env.example: {e}")
            return False
    else:
        print("❌ .env.example not found")
        return False
    
    # 檢查 .env
    env_path = Path(".env")
    if env_path.exists():
        print("✅ .env exists")
    else:
        print("⚠️ .env not found (copy from .env.example)")
    
    return True


def generate_build_commands():
    """生成建置命令"""
    print("\n🔧 Docker Build Commands:")
    print("=" * 50)
    
    commands = [
        "# Test configuration",
        "docker-compose config",
        "",
        "# Build services (no cache)",
        "docker-compose build --no-cache mcp-server",
        "docker-compose build --no-cache vision-agent", 
        "docker-compose build --no-cache playwright-crawler-agent",
        "",
        "# Build services (with cache)",
        "docker-compose build mcp-server",
        "docker-compose build vision-agent",
        "docker-compose build playwright-crawler-agent",
        "",
        "# Start services",
        "docker-compose up -d postgres redis rustfs",
        "docker-compose up -d mcp-server",
        "docker-compose up -d vision-agent playwright-crawler-agent",
        "",
        "# Check status",
        "docker-compose ps",
        "docker-compose logs mcp-server",
        "docker-compose logs vision-agent",
        "docker-compose logs playwright-crawler-agent",
        "",
        "# Test health",
        "curl http://localhost:10100/health",
        "curl http://localhost:8005/health", 
        "curl http://localhost:8006/health",
        "",
        "# Stop services",
        "docker-compose down"
    ]
    
    for command in commands:
        print(command)


def main():
    """主函數"""
    print("🚀 Docker Configuration Verification")
    print("=" * 50)
    
    checks = [
        ("Docker Compose Syntax", check_docker_compose_syntax),
        ("Required Files", check_required_files),
        ("Docker Compose Analysis", analyze_docker_compose),
        ("Environment Variables", check_environment_variables)
    ]
    
    results = {}
    
    for check_name, check_func in checks:
        try:
            results[check_name] = check_func()
        except Exception as e:
            print(f"❌ {check_name} failed with error: {e}")
            results[check_name] = False
    
    # 總結
    print("\n" + "=" * 50)
    print("📊 Verification Summary")
    print("=" * 50)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for check_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {check_name}")
    
    print(f"\nOverall: {passed}/{total} checks passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("\n🎉 All checks passed! Docker configuration looks good.")
        generate_build_commands()
    elif passed >= total * 0.8:
        print("\n⚠️ Most checks passed. Fix remaining issues before building.")
        generate_build_commands()
    else:
        print("\n❌ Multiple issues found. Please fix configuration before building.")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)