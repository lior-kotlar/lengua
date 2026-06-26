import { Link } from 'react-router-dom';

export default function Login() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Log in</h1>
      <p className="text-sm text-muted-foreground">
        Sign-in with email, password, and OAuth lands in a later group.
      </p>
      <p className="text-sm">
        Need an account?{' '}
        <Link to="/signup" className="font-medium underline underline-offset-4">
          Sign up
        </Link>
      </p>
    </div>
  );
}
