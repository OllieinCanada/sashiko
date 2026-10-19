
    #[test]
    fn test_det6_malformed_identity_and_id_errors_do_not_echo_inputs() {
        let marker = "DET6_FAKE_CREDENTIAL_CANARY";
        let mut invalid = vec![
            format!("{marker}\r\nInjected: value@example.test"),
            format!("{marker}\0@example.test"),
            format!("{marker}@-invalid.test"),
            format!("{marker}@@example.test"),
            format!("{marker} @example.test"),
            format!("{marker}@localhost"),
            format!("{marker}@\u{2603}.test"),
            format!("{marker}{}", "x".repeat(1025)),
        ];
        for byte in 0..=31_u8 {
            invalid.push(format!("{marker}{}@example.test", char::from(byte)));
        }
        invalid.push(format!("{marker}{}@example.test", char::from(127)));
        for author in invalid {
            let error = author_key(&author).unwrap_err().to_string();
            assert!(!error.contains(marker));
        }
        for message in ["".into(), format!("{marker}\r\nInjected"), format!("{marker} x"),
            format!("{marker}\0"), format!("{marker}<x"), "x".repeat(999)] {
            assert!(message_key(&message).is_err());
            assert!(!message_key(&message).unwrap_err().to_string().contains(marker));
        }
        let valid = author_key("O'Hara <O'HARA@EXAMPLE.TEST>").unwrap();
        assert_eq!(valid, "o'hara@example.test");
        assert_eq!(message_key("<safe');SELECT(1);--@example.test>").unwrap(),
            "safe');SELECT(1);--@example.test");
    }
