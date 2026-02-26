import { Link } from 'react-router-dom';

export default function Privacy() {
  return (
    <div className="min-h-screen bg-surface-50 text-white px-5 py-20">
      <div className="max-w-3xl mx-auto">
        <Link to="/" className="text-brand-400 hover:text-brand-300 text-[13px] mb-10 inline-block font-medium">
          ← Back to Tubevo
        </Link>

        <h1 className="text-[32px] font-bold mb-2 tracking-tight">Privacy Policy</h1>
        <p className="text-surface-600 text-[14px] mb-10">Last updated: February 23, 2026</p>

        <div className="space-y-8 text-surface-700 text-[14px] leading-relaxed">
          <section>
            <h2 className="text-[18px] font-semibold text-white mb-3">1. Introduction</h2>
            <p>
              Tubevo ("we", "our", or "us") operates the website tubevo.us and provides
              automated YouTube content creation and publishing services. This Privacy Policy
              explains how we collect, use, disclose, and safeguard your information when you
              use our service.
            </p>
          </section>

          <section>
            <h2 className="text-[18px] font-semibold text-white mb-3">2. Information We Collect</h2>
            <p className="mb-2">We collect the following types of information:</p>
            <ul className="list-disc list-inside space-y-1 ml-2">
              <li><strong>Account Information:</strong> Email address, name, and password when you create an account.</li>
              <li><strong>Payment Information:</strong> Billing details processed securely through Stripe. We do not store your credit card numbers.</li>
              <li><strong>YouTube Data:</strong> When you connect your YouTube account via Google OAuth, we access your YouTube channel to upload videos on your behalf. We only request the permissions necessary to provide our service.</li>
              <li><strong>Usage Data:</strong> Information about how you interact with our service, including videos created, schedules set, and features used.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-[18px] font-semibold text-white mb-3">3. How We Use Your Information</h2>
            <ul className="list-disc list-inside space-y-1 ml-2">
              <li>To provide, maintain, and improve our services</li>
              <li>To create and upload YouTube videos on your behalf</li>
              <li>To process payments and manage your subscription</li>
              <li>To communicate with you about your account and our services</li>
              <li>To detect, prevent, and address technical issues</li>
            </ul>
          </section>

          <section>
            <h2 className="text-[18px] font-semibold text-white mb-3">4. Google API Services - User Data Policy</h2>
            <p>
              Tubevo's use and transfer to any other app of information received from Google APIs
              will adhere to the{' '}
              <a
                href="https://developers.google.com/terms/api-services-user-data-policy"
                target="_blank"
                rel="noopener noreferrer"
                className="text-brand-400 hover:text-brand-300 underline"
              >
                Google API Services User Data Policy
              </a>
              , including the Limited Use requirements. We only access YouTube data necessary to
              provide our video uploading service, and we do not share this data with third parties.
            </p>
          </section>

          <section>
            <h2 className="text-[18px] font-semibold text-white mb-3">5. Data Sharing</h2>
            <p>We do not sell your personal information. We may share data with:</p>
            <ul className="list-disc list-inside space-y-1 ml-2">
              <li><strong>Service Providers:</strong> Stripe (payments), Google/YouTube (video uploads), OpenAI (content generation), ElevenLabs (voiceovers), Pexels (stock footage).</li>
              <li><strong>Legal Requirements:</strong> When required by law or to protect our rights.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-[18px] font-semibold text-white mb-3">6. Data Security</h2>
            <p>
              We implement industry-standard security measures to protect your data, including
              encrypted connections (HTTPS), hashed passwords, and secure token storage.
              However, no method of transmission over the Internet is 100% secure.
            </p>
          </section>

          <section>
            <h2 className="text-[18px] font-semibold text-white mb-3">7. Data Retention & Deletion</h2>
            <p>
              We retain your data for as long as your account is active. You may request deletion
              of your account and associated data at any time by contacting us at{' '}
              <a href="mailto:support@tubevo.us" className="text-brand-400 hover:text-brand-300 underline">
                support@tubevo.us
              </a>.
            </p>
          </section>

          <section>
            <h2 className="text-[18px] font-semibold text-white mb-3">8. Your Rights</h2>
            <p>You have the right to:</p>
            <ul className="list-disc list-inside space-y-1 ml-2">
              <li>Access the personal data we hold about you</li>
              <li>Request correction of inaccurate data</li>
              <li>Request deletion of your data</li>
              <li>Revoke YouTube/Google access at any time via your Google Account settings</li>
            </ul>
          </section>

          <section>
            <h2 className="text-[18px] font-semibold text-white mb-3">9. Changes to This Policy</h2>
            <p>
              We may update this Privacy Policy from time to time. We will notify you of any
              changes by posting the new policy on this page and updating the "Last updated" date.
            </p>
          </section>

          <section>
            <h2 className="text-[18px] font-semibold text-white mb-3">10. Contact Us</h2>
            <p>
              If you have questions about this Privacy Policy, please contact us at{' '}
              <a href="mailto:support@tubevo.us" className="text-brand-400 hover:text-brand-300 underline">
                support@tubevo.us
              </a>.
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
