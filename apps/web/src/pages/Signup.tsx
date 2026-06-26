import { Link } from 'react-router-dom';

export default function Signup() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Sign up</h1>
      <p className="text-sm text-muted-foreground">
        Account creation and email verification land in a later group.
      </p>
      <p className="text-sm">
        Already have an account?{' '}
        <Link to="/login" className="font-medium underline underline-offset-4">
          Log in
        </Link>
      </p>
    </div>
  );
}
