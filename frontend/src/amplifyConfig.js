import { Amplify } from 'aws-amplify';

// FaceLivenessDetector uses Amplify Auth (a Cognito Identity Pool) solely to
// sign the StartFaceLivenessSession request to Rekognition. Unauthenticated
// (guest) identities must be enabled on the pool.
export function configureAmplify() {
  Amplify.configure({
    Auth: {
      Cognito: {
        identityPoolId: import.meta.env.VITE_COGNITO_IDENTITY_POOL_ID,
        allowGuestAccess: true,
      },
    },
  });
}

export const AWS_REGION = import.meta.env.VITE_AWS_REGION || 'us-east-1';
