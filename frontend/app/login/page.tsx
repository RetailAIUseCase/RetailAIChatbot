"use client";

import type React from "react";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Eye, EyeOff } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Header } from "@/components/ui/header";
import Image from "next/image";
import bgImage5 from "@/public/loginbackgroundv5.jpg";
import smarterIcon from "@/public/smarter.png";
import connectedIcon from "@/public/connected.png";
import supplyIcon from "@/public/supply.png";
import alertIcon from "@/public/alerts.png";

// Add this interface for the login response
interface LoginResponse {
  access_token: string;
  token_type: string;
}

export default function LoginPage() {
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [error, setError] = useState("");

  // Login state
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");

  // Register state
  const [registerEmail, setRegisterEmail] = useState("");
  const [registerPassword, setRegisterPassword] = useState("");
  const [registerConfirmPassword, setRegisterConfirmPassword] = useState("");
  const [fullName, setFullName] = useState("");

  // API base URL
  const API_BASE_URL =
    process.env.NEXT_PUBLIC_API_URL || "https://retail-ai-chatbot.onrender.com";

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email: loginEmail,
          password: loginPassword,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        // Store token in localStorage or secure cookie
        localStorage.setItem("access_token", data.access_token);
        console.log("Login successful:", { email: loginEmail });
        router.push("/dashboard");
      } else {
        const errorData = await response.json();
        console.log("Login failed:", errorData.detail);
        console.error("Login failed:", errorData.detail);
        alert(`Login failed: ${errorData.detail}`);
        // Handle error (show toast, etc.)
      }
    } catch (error) {
      console.error("Login error:", error);
      alert("Network error occurred. Please check if the backend is running.");
      // Handle network error
    } finally {
      setIsLoading(false);
    }
  };
  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    // Validation
    if (registerPassword !== registerConfirmPassword) {
      alert("Passwords don't match!");
      setIsLoading(false);
      return;
    }

    if (registerPassword.length < 6) {
      alert("Password must be at least 6 characters long!");
      setIsLoading(false);
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/auth/register`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email: registerEmail,
          password: registerPassword,
          full_name: fullName || null,
        }),
      });
      if (response.ok) {
        const userData = await response.json();
        console.log("Registration successful:", userData);

        // Auto-login after successful registration
        const loginResponse = await fetch(`${API_BASE_URL}/auth/login`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            email: registerEmail,
            password: registerPassword,
          }),
        });

        if (loginResponse.ok) {
          const loginData = await loginResponse.json();
          localStorage.setItem("access_token", loginData.access_token);
          localStorage.setItem("token_type", loginData.token_type);

          alert("Registration successful! You are now logged in.");
          router.push("/dashboard");
        } else {
          alert("Registration successful! Please login with your credentials.");
          // Switch to login tab
          const loginTab = document.querySelector(
            '[data-tab="login"]'
          ) as HTMLElement;
          loginTab?.click();
        }
      } else {
        const errorData = await response.json();
        console.error("Registration failed:", errorData.detail);
        alert(`Registration failed: ${errorData.detail}`);
      }
    } catch (error) {
      console.error("Registration error:", error);
      alert("Network error occurred. Please check if the backend is running.");
    } finally {
      setIsLoading(false);
    }
  };
  // try {
  // ***********************************************************************************************
  // For local development
  // const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

  // // For production, you would use:
  // // const apiUrl = process.env.NEXT_PUBLIC_API_URL || "https://your-railway-app.up.railway.app"

  // const formData = new FormData()
  // formData.append("username", email)
  // formData.append("password", password)

  // const response = await fetch(`${apiUrl}/auth/login`, {
  //   method: "POST",
  //   body: formData,
  // })

  // if (!response.ok) {
  //   const errorData = await response.json()
  //   throw new Error(errorData.detail || "Login failed")
  // }

  // const data: LoginResponse = await response.json()

  // // Store the token in localStorage or cookies
  // localStorage.setItem("access_token", data.access_token)

  // console.log("Login successful:", { email })
  // router.push("/dashboard")
  // ***********************************************************************************************

  // Simulate login API call
  //     await new Promise((resolve) => setTimeout(resolve, 1000))

  //     // For demo purposes, accept any email/password combination
  //     if (email && password) {
  //       console.log("Login successful:", { email })
  //       router.push("/dashboard")
  //     } else {
  //       console.log("Login failed: Missing credentials")
  //     }
  //   } catch (error) {
  //     console.error("Login error:", error)
  //   } finally {
  //     setIsLoading(false)
  //   }
  // }

  return (
    <div className="relative min-h-screen w-full">
      {/* Background Image */}
      <Image
        src={bgImage5}
        alt="Background"
        fill
        priority
        className="object-cover -z-10 filter brightness-50"
      />
      <div className="min-h-screen max-w-full flex flex-col items-center relative z-10">
        <Header className="w-full mb-8"></Header>
        <div className="w-full lg:max-w-6xl grid lg:grid-cols-5 gap-8 items-start mx-12 my-10">
          {/* Left side - Branding and Features */}
          <div className="flex justify-center flex-col gap-10 lg:col-span-3">
            <div className="flex flex-col gap-6">
              <h1 className="text-3xl font-bold text-background">
                Supply Chain Intelligence Assistant
              </h1>
              <p className="text-xl text-background relaxed">
                Empowers every role in the supply chain
              </p>
            </div>

            <div className="space-y-6">
              <div className="flex items-start gap-4">
                <div className="bg-primary/10 rounded-lg">
                  <Image
                    src={smarterIcon.src}
                    alt="smarter-icon"
                    width="40"
                    height="40"
                  />
                </div>
                <div>
                  <h3 className="font-semibold text-background text-sm">
                    Faster, Smarter Decision-Making
                  </h3>
                  <p className="text-background text-sm">
                    Replaces manual searches and cross-system queries with
                    prompt-driven workflows
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-4">
                <div className="bg-primary/10 rounded-lg">
                  <Image
                    src={supplyIcon.src}
                    alt="connected-icon"
                    width="40"
                    height="40"
                  />
                </div>
                <div>
                  <h3 className="font-semibold text-background text-sm">
                    Unified View of Supply Chain Data
                  </h3>
                  <p className="text-background text-sm">
                    Connects ERP, WMS, TMS, MES and even spreadsheets into one
                    queryable chat without system-hopping
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-4">
                <div className="bg-primary/10 rounded-lg">
                  <Image
                    src={connectedIcon.src}
                    alt="supply-icon"
                    width="40"
                    height="40"
                  />
                </div>
                <div>
                  <h3 className="font-semibold text-background text-sm">
                    Semi Autonomous Connected journey
                  </h3>
                  <p className="text-background text-sm">
                    Orchestrates all steps of supply chain, automating within
                    guardrail, and escalating when needed
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-4">
                <div className="bg-primary/10 rounded-lg">
                  <Image
                    src={alertIcon.src}
                    alt="supply-icon"
                    width="40"
                    height="40"
                  />
                </div>
                <div>
                  <h3 className="font-semibold text-background text-sm">
                    Natural-Language Alerts
                  </h3>
                  <p className="text-background text-sm">
                    Create alert rules by typing a prompt and get notified, no
                    forms or dashboards
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Right side - Login Form */}
          <div className="flex justify-center lg:col-span-2">
            <Card className="w-full max-w-xl">
              <CardHeader className="space-y-2 text-center">
                <CardTitle className="text-2xl font-bold">Sign in</CardTitle>
                <CardDescription>
                  Sign in to your account or create a new one
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Tabs defaultValue="login" className="space-y-4">
                  <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="login" data-tab="login">
                      Login
                    </TabsTrigger>
                    <TabsTrigger value="register">Register</TabsTrigger>
                  </TabsList>

                  {/* Login Tab */}
                  <TabsContent value="login">
                    <form onSubmit={handleLogin} className="space-y-4">
                      <div className="space-y-2">
                        <Label htmlFor="login-email">Email</Label>
                        <Input
                          id="login-email"
                          type="email"
                          placeholder="Enter your email"
                          value={loginEmail}
                          onChange={(e) => setLoginEmail(e.target.value)}
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="login-password">Password</Label>
                        <div className="relative">
                          <Input
                            id="login-password"
                            type={showPassword ? "text" : "password"}
                            placeholder="Enter your password"
                            value={loginPassword}
                            onChange={(e) => setLoginPassword(e.target.value)}
                            required
                          />
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                            onClick={() => setShowPassword(!showPassword)}
                          >
                            {showPassword ? (
                              <EyeOff className="h-4 w-4 text-muted-foreground" />
                            ) : (
                              <Eye className="h-4 w-4 text-muted-foreground" />
                            )}
                          </Button>
                        </div>
                      </div>
                      <Button
                        type="submit"
                        className="w-full"
                        disabled={isLoading}
                      >
                        {isLoading ? "Signing In..." : "Sign In"}
                      </Button>
                    </form>
                  </TabsContent>

                  {/* Register Tab */}
                  <TabsContent value="register">
                    <form onSubmit={handleRegister} className="space-y-4">
                      <div className="space-y-2">
                        <Label htmlFor="full-name">Full Name (Optional)</Label>
                        <Input
                          id="full-name"
                          type="text"
                          placeholder="Enter your full name"
                          value={fullName}
                          onChange={(e) => setFullName(e.target.value)}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="register-email">Email</Label>
                        <Input
                          id="register-email"
                          type="email"
                          placeholder="Enter your email"
                          value={registerEmail}
                          onChange={(e) => setRegisterEmail(e.target.value)}
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="register-password">Password</Label>
                        <div className="relative">
                          <Input
                            id="register-password"
                            type={showPassword ? "text" : "password"}
                            placeholder="Enter your password (min 6 characters)"
                            value={registerPassword}
                            onChange={(e) =>
                              setRegisterPassword(e.target.value)
                            }
                            required
                            minLength={6}
                          />
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                            onClick={() => setShowPassword(!showPassword)}
                          >
                            {showPassword ? (
                              <EyeOff className="h-4 w-4 text-muted-foreground" />
                            ) : (
                              <Eye className="h-4 w-4 text-muted-foreground" />
                            )}
                          </Button>
                        </div>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="confirm-password">
                          Confirm Password
                        </Label>
                        <Input
                          id="confirm-password"
                          type={showPassword ? "text" : "password"}
                          placeholder="Confirm your password"
                          value={registerConfirmPassword}
                          onChange={(e) =>
                            setRegisterConfirmPassword(e.target.value)
                          }
                          required
                        />
                      </div>
                      <Button
                        type="submit"
                        className="w-full"
                        disabled={isLoading}
                      >
                        {isLoading ? "Creating Account..." : "Create Account"}
                      </Button>
                    </form>
                  </TabsContent>
                </Tabs>

                <div className="text-center">
                  <Button
                    variant="link"
                    className="text-sm text-muted-foreground"
                  >
                    Forgot your password?
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
